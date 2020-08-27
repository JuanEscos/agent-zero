import git
import ray
from ray import tune
from ray.tune import CLIReporter

from src.deepq.config import Config, GPU_SIZE
from src.deepq.trainer import Trainer
from src.common.utils import parse_arguments


def trial_str_creator(trial, sha):
    return "{}_{}_{}_{}".format(trial.trainable_name, trial.config['game'], sha, trial.trial_id)


if __name__ == '__main__':
    repo = git.Repo(search_parent_directories=True)
    sha = repo.git.rev_parse(repo.head.object.hexsha, short=True)
    sha_long = repo.head.object.hexsha

    cfg = Config(sha=sha_long)
    args = parse_arguments(cfg)
    cfg = Config(**vars(args))
    cfg.update()

    if isinstance(cfg.game, list):
        cfg.game = tune.grid_search(cfg.game)

    ray.init(memory=20 * 2 ** 30, object_store_memory=80 * 2 ** 30)
    reporter = CLIReporter(
        metric_columns=["frames", "loss", "ep_reward_test", "ep_reward_train",
                        "ep_reward_train_max", "time_past", "time_remain", "speed", "velocity", "epsilon", "qmax"])

    tune.run(
        Trainer,
        name=cfg.exp_name,
        verbose=1,
        checkpoint_at_end=True,
        fail_fast=True,
        reuse_actors=True,
        restore=cfg.restore_checkpoint,
        stop=lambda trial_id, result: result['frames'] > cfg.total_steps,
        checkpoint_freq=1000,
        trial_name_creator=tune.function(lambda trial: trial_str_creator(trial, sha)),
        progress_reporter=reporter,
        resources_per_trial={"gpu": 1.0 / GPU_SIZE, "extra_gpu": 1.0 / GPU_SIZE},
        config=vars(cfg),
    )