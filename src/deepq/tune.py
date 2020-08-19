import argparse
import json
import random

import ray
from ray import tune
from ray.tune import CLIReporter
from ray.tune.schedulers import PopulationBasedTraining

from src.deepq.config import Config
from src.deepq.trainer import Trainer


def parse_arguments():
    cfg = Config()
    parser = argparse.ArgumentParser()
    for k, v in vars(cfg).items():
        parser.add_argument(f"--{k}", type=type(v), default=v)
    args = parser.parse_args()
    print("input args:\n", json.dumps(vars(args), indent=4, separators=(",", ":")))
    return vars(args)


if __name__ == '__main__':
    kwargs = parse_arguments()
    cfg = Config(**kwargs)
    ray.init(memory=20 * 2 ** 30, object_store_memory=80 * 2 ** 30)
    reporter = CLIReporter(
        metric_columns=["game", "frames", "loss", "ep_reward_test", "ep_reward_train", "ep_reward_test_max",
                        "time_past",
                        "time_remain", "speed", "epsilon", "adam_lr", "qmax"]
    )

    pbt_scheduler = PopulationBasedTraining(
        time_attr='training_iteration',
        metric='ep_reward_train',
        mode='max',
        perturbation_interval=100,
        hyperparam_mutations={
            "adam_lr": lambda: random.uniform(1e-5, 1e-3),
        })

    analysis = tune.run(
        Trainer,
        name='atari_deepq_tune',
        verbose=1,
        stop=lambda trial_id, result: result['frames'] > kwargs['total_steps'],
        checkpoint_at_end=True,
        progress_reporter=reporter,
        checkpoint_freq=800,
        reuse_actors=True,
        scheduler=pbt_scheduler,
        resources_per_trial={"gpu": 3},
        fail_fast=True,
        config={
            "adam_lr": tune.grid_search([5e-5, 1e-4, 2e-4, 5e-4]),
            "game": kwargs['game']
        }
    )
