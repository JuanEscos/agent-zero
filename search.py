import argparse
import json

import ray
from ray import tune
from ray.tune import CLIReporter
from ray.tune import Stopper

from src.deepq.agent import default_hyperparams, Trainer


def parse_arguments(params):
    parser = argparse.ArgumentParser()
    for k, v in params.items():
        parser.add_argument(f"--{k}", type=type(v), default=v)
    args = parser.parse_args()
    print("input args:\n", json.dumps(vars(args), indent=4, separators=(",", ":")))
    return vars(args)


class CustomStopper(Stopper):
    def __init__(self, max_frames):
        self.should_stop = False
        self.max_frames = max_frames

    def __call__(self, trial_id, result):
        if not self.should_stop and result['frames'] > int(1e5):
            self.should_stop = True
        return self.should_stop

    def stop_all(self):
        return self.should_stop


if __name__ == '__main__':
    params = default_hyperparams()
    kwargs = parse_arguments(params)
    ray.init(memory=20 * 2 ** 30, object_store_memory=80 * 2 ** 30)
    # stopper = CustomStopper(kwargs['total_steps'])
    reporter = CLIReporter(
        metric_columns=["exploration_ratio", "adam_lr", "lr", "agent_train_freq", "frames", "loss", "ep_reward_test",
                        "ep_reward_train"])

    analysis = tune.run(
        Trainer,
        name=kwargs['exp_name'],
        verbose=0,
        checkpoint_at_end=True,
        fail_fast=True,
        stop={'training_iteration': kwargs['epoches'] * (1 + kwargs['num_actors'])},
        # stop = {'training_iteration': self.epoches * (self.num_actors + 1)},
        checkpoint_freq=800,
        config={
            "exploration_ratio": tune.grid_search([0.1, 0.15]),
            "adam_lr": tune.grid_search([5e-4, 1e-4, 2e-4]),
            "agent_train_freq": tune.grid_search([15, 10]),
            "game": tune.grid_search(["Breakout"])
        },
        progress_reporter=reporter,
        resources_per_trial={"gpu": 3},
    )

    print("Best config: ", analysis.get_best_config(metric="ep_reward_test"))
    df = analysis.dataframe()
    df.to_csv('out.csv')
