import random
from collections import deque

import numpy as np
import torch
from agent0.common.utils import LinearSchedule
from lz4.block import decompress, compress
from torch.utils.data import Dataset, Sampler


class ReplayDataset(Dataset, Sampler):
    def __init__(self, obs_shape, replay_size, batch_size=256, prioritize=False,
                 priority_beta0=0.4, priority_alpha=0.5, total_steps=int(1e7)):
        self.obs_shape = obs_shape
        self.prioritize = prioritize
        self.replay_size = replay_size
        self.batch_size = batch_size
        self.priority_alpha = priority_alpha

        if len(obs_shape) > 1:
            self.frames_shape = (obs_shape[0] * 2, obs_shape[1], obs_shape[2])
        self.data = deque(maxlen=replay_size)
        self.best_ep = deque(maxlen=replay_size // 4)
        self.top = 0

        if self.prioritize:
            self.beta_schedule = LinearSchedule(priority_beta0, 1.0, total_steps)
            # noinspection PyArgumentList
            self.prob = torch.ones(self.replay_size)
            self.beta = priority_beta0
            self.max_p = 1.0

    def __len__(self):
        return self.top

    def __getitem__(self, idx):
        idx = idx % self.top

        frames, at, rt, dt = self.data[idx]
        if len(self.obs_shape) > 1:
            frames = np.frombuffer(decompress(frames), dtype=np.uint8).reshape(self.frames_shape)

        if len(self.best_ep) > 0:
            st_best, at_best = random.sample(self.best_ep)
            st_best = np.frombuffer(decompress(st_best), dtype=np.uint8).reshape(self.obs_shape)
        else:
            st_best = np.zeros(self.obs_shape)
            at_best = 0

        if self.prioritize:
            weight = self.prob[idx]
        else:
            weight = 1.0

        return np.array(frames), at, rt, dt, weight, idx, st_best, at_best

    def __iter__(self):
        for _ in range(self.top // self.batch_size):
            yield torch.multinomial(self.prob[:self.top], self.batch_size, False).tolist()

    def extend_ep_best(self, ep_best):
        for ep in ep_best:
            frames, actions = ep
            ep_len = len(actions)
            frames_shape = (ep_len,) + self.obs_shape
            frames = np.frombuffer(decompress(frames), dtype=np.uint8).reshape(frames_shape)
            for st, at in zip(frames, actions):
                self.best_ep.append((compress(st), at))

    def extend(self, transitions):
        self.data.extend(transitions)
        num_entries = len(transitions)
        self.top = min(self.top + num_entries, self.replay_size)

        if self.prioritize:
            self.prob.roll(-num_entries, 0)
            self.prob[-num_entries:] = self.max_p ** self.priority_alpha
            self.beta = self.beta_schedule(num_entries)

    def update_priorities(self, idxes, priorities):
        self.prob[idxes] = priorities.add(1e-8).pow(self.priority_alpha)
        self.max_p = max(priorities.max().item(), self.max_p)
