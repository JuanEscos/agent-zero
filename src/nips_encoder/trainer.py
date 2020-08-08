from collections import deque

import gym
import numpy as np
import torch
import torch.nn.functional as F
from ray import tune
from tqdm import tqdm

from src.common.utils import ReplayDataset, DataPrefetcher, DataLoaderX, make_env
from src.common.vec_env import ShmemVecEnv
from src.nips_encoder.model import ModelEncoder


def default_hyperparams():
    params = dict(
        game='Breakout',
        epoches=50,
        batch_size=128,
        num_envs=32,
        replay_size=int(1e6),
        adam_lr=1e-4,
        num_data_workers=4,
        pin_memory=True,
        optim='adam')
    return params


class Trainer(tune.Trainable):
    def _setup(self, config):
        kwargs = default_hyperparams()
        for k, v in config.items():
            kwargs[k] = v

        for k, v in kwargs.items():
            setattr(self, k, v)

        self.device = torch.device('cuda:0')
        self.env = gym.make(f'{self.game}NoFrameskip-v4')
        self.action_dim = self.env.action_space.n

        self.model = ModelEncoder(self.action_dim).to(self.device)
        self.replay = deque(maxlen=self.replay_size)

        if self.optim == 'adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), self.adam_lr)
        elif self.optim == 'adamw':
            self.optimizer = torch.optim.AdamW(self.model.parameters(), self.adam_lr)
        else:
            raise ValueError("No such optimizer")

        self.sample_replay()

    def sample_replay(self):
        self.envs = ShmemVecEnv([lambda: make_env(self.game, False, False)
                                 for _ in range(self.num_envs)], context='fork')

        print("Sampling replay")
        obs = self.envs.reset()
        step = 0
        steps = int(1e6) // self.num_envs + 1
        for step in tqdm(range(steps)):
            action_random = np.random.randint(0, self.action_dim, self.num_envs)
            obs_next, reward, done, info = self.envs.step(action_random)

            for entry in zip(obs, action_random, reward, obs_next, done):
                self.replay.append(entry)

        print("Done")
        self.envs.close()

    def get_datafetcher(self):
        dataset = ReplayDataset(self.replay)
        self.dataloader = DataLoaderX(dataset, batch_size=self.batch_size, shuffle=True,
                                      num_workers=self.num_data_workers, pin_memory=self.pin_memory)

        datafetcher = DataPrefetcher(self.dataloader, self.device)
        return datafetcher

    def _train(self):
        try:
            data = self.prefetcher.next()
        except:
            self.prefetcher = self.get_datafetcher()
            data = self.prefetcher.next()

        states, actions, rewards, next_states, terminals = data
        states = states.float().div(255.0)
        next_states = next_states.float().div(255.0)
        actions = actions.long()

        states_pred = self.model(states, actions)

        loss = F.mse_loss(states_pred, next_states)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        result = dict(
            loss=loss.item(),
            adam_lr=self.adam_lr,
            epoch=(self._iteration * self.batch_size) // self.replay_size,
            speed=self._iteration * self.batch_size / (self._time_total + 1),
            time_past=self._time_total,
            time_remain=(self.epoches * self.replay_size - self._iteration * self.batch_size) / (
                    (self._iteration * self.batch_size) / (self._time_total + 1)),
        )
        return result

    def _stop(self):
        epoch = (self._iteration * self.batch_size) / len(self.replay)
        if epoch > self.epoches:
            torch.save({
                'model': self.model.state_dict()
            }, './final.pth')

    def _save(self, checkpoint_dir):
        return {
            'model': self.model.state_dict(),
            'optim': self.optimizer.state_dict()
        }

    def _restore(self, checkpoint):
        self.model.load_state_dict(checkpoint['model'])
        self.optimizer.load_state_dict(checkpoint['optim'])

    def reset_config(self, new_config):
        if "adam_lr" in new_config:
            self.adam_lr = new_config['adam_lr']
            for param_group in self.optimizer.param_groups:
                param_group['lr'] = new_config['adam_lr']

        self.config = new_config
        return True
