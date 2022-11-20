import argparse
import os
import random
from tqdm import tqdm
from Utils import *

def get_file_move_command(unparsed_args):
    """Returns a (file_move_command, unparsed_args) tuple, where
    [file_move_command] can be run to move files onto the compute node, and
    [unparsed_args] is the input [unparsed_args] but modified to use the data on
    the compute node.

    Supposing [unparsed_args] were parsed, the command will move the file
    specified by the value of each key that begins with 'data_' onto the compute
    node. The returned [unparsed_args] specify the path on the compute node
    instead.

    On ComputeCanada, this gives about 2x the performance.
    """
    arg2idx = {a: idx for idx,a in enumerate(unparsed_args)}
    data_args = {a for a in unparsed_args if a.startswith("--data_")}

    source2dest = {}
    for d in data_args:
        source = unparsed_args[arg2idx[d] + 1]
        dest = source.replace(os.path.dirname(os.path.dirname(source)), "")
        dest = dest.lstrip("/")
        source2dest[source] = f"$SLURM_TMPDIR/{dest}"
        unparsed_args[arg2idx[d] + 1] = f"$SLURM_TMPDIR/{dest}"

    s = "\n".join([f"mkdir {os.path.dirname(d)}\ncp {s} {d}"
        for s,d in source2dest.items()])
    return s, unparsed_args

def get_time(hours):
    """Returns [hours] in SLURM string form.
    
    Args:
    hours   (int) -- the number of hours to run one chunk for
    """
    total_seconds = (hours * 3600) - 1
    days = total_seconds // (3600 * 24)
    total_seconds = total_seconds % (3600 * 24)
    hours = total_seconds // 3600
    total_seconds = total_seconds % 3600
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{days}-{hours}:{minutes}:{seconds}"

if __name__ == "__main__":
    P = argparse.ArgumentParser()
    P.add_argument("script",
        help="Script to run")
    P.add_argument("--time", type=int, default=3,
        help="Number of hours per task")
    P.add_argument("--parallel", type=int, default=1,
        help="Number of tasks to run in parallel")
    P.add_argument("--account", default="rrg-keli", choices=["def-keli", "rrg-keli"],
        help="ComputeCanada account to run on")
    P.add_argument("--end_chunk", default=0, type=int,
        help="Index of last chunk to run, with zero-indexing")
    P.add_argument("--start_chunk", default=0, type=int,
        help="Index of the chunk to resume from, ie. where there was an error")
    P.add_argument("--cluster", choices=["narval", "cedar"], default="narval",
        help="Cluster on which the jobs are submitted")
    P.add_argument("--nproc_per_node", type=int, default=4,
        help="Number of GPUs per node")
    P.add_argument("--use_torch_distributed", type=int, choices=[0, 1], default=0,
        help="Whether to launch with 'python -m torch.distributed.launch' or with 'python'")
    submission_args, unparsed_args = P.parse_known_args()

    ############################################################################
    # Figure out the commands to instantiate the required Python environment
    # based on the given cluster, the command to launch training on the compute
    # node(s), and initialize the command to move files onto the compute node.
    ############################################################################
    tqdm.write(f"Will use Python environment setup for cluster {submission_args.cluster}")
    if submission_args.cluster == "cedar":
        PYTHON_ENV_STR = "module load python/3.9\nsource ~/py310URSA/bin/activate"
        GPU_TYPE = "v100l"
    elif submission_args.cluster == "narval":
        PYTHON_ENV_STR = "conda activate py310URSA"
        GPU_TYPE = "a100"
    else:
        raise ValueError(f"Unknown cluster {submission_args.cluster}")

    if submission_args.use_torch_distributed:
        launch_command = f"python -m torch.distributed.launch --nproc_per_node={submission_args.nproc_per_node}"
    else:
        launch_command = "python"

    file_move_command = None

    ############################################################################
    # Get script-specific argument settings
    ############################################################################
    if submission_args.script == "LinearProbe.py":
        from LinearProbe import get_args, get_linear_probe_folder

        unparsed_args += [f"--world_size", f"{submission_args.nproc_per_node}"]

        file_move_command, unparsed_args = get_file_move_command(unparsed_args)
        args = get_args(unparsed_args)

        START_CHUNK = "0"
        END_CHUNK = "0"
        PARALLEL = "1"
        NUM_GPUS = str(submission_args.nproc_per_node)
        NAME = get_linear_probe_folder(args, make_folder=False)
        NAME = NAME.replace(f"{project_dir}/models/", "").replace("/", "_")

        SCRIPT = f"{file_move_command}\n{launch_command} {submission_args.script} {' '.join(unparsed_args)}"
        
        template = f"{os.path.dirname(__file__)}/slurm/slurm_template_sequential.txt"
        with open(template, "r") as f:
            template = f.read()
    elif submission_args.script == "TrainIMLE.py":
        from TrainIMLE import get_args, model_folder

        file_move_command, unparsed_args = get_file_move_command(unparsed_args)
        args = get_args(unparsed_args)

        unparsed_args += [f"--job_id", "$SLURM_ARRAY_JOB_ID"]

        START_CHUNK = "0"
        END_CHUNK = "0"
        PARALLEL = "1"
        NUM_GPUS = str(len(args.gpus))
        NAME = model_folder(args, make_folder=False)
        NAME = NAME.replace(f"{args.save_folder}/models/", "").replace("/", "_")
        
        SCRIPT = f"{file_move_command}\n{launch_command} {submission_args.script} {' '.join(unparsed_args)}"
        
        template = f"{os.path.dirname(__file__)}/slurm/slurm_template_sequential.txt"
        with open(template, "r") as f:
            template = f.read()
    elif submission_args.script == "TrainIMLE32.py":
        from TrainIMLE32 import get_args, model_folder

        file_move_command, unparsed_args = get_file_move_command(unparsed_args)
        args = get_args(unparsed_args)

        unparsed_args += [f"--job_id", "$SLURM_ARRAY_JOB_ID"]

        START_CHUNK = "0"
        END_CHUNK = "0"
        PARALLEL = "1"
        NUM_GPUS = str(len(args.gpus))
        NAME = model_folder(args, make_folder=False)
        NAME = NAME.replace(f"{project_dir}/models/", "").replace("/", "_")
        
        SCRIPT = f"{file_move_command}\n{launch_command} {submission_args.script} {' '.join(unparsed_args)}"
        
        template = f"{os.path.dirname(__file__)}/slurm/slurm_template_sequential.txt"
        with open(template, "r") as f:
            template = f.read()
    else:
        raise ValueError(f"Unknown script '{submission_args.script}")

    template = template.replace("SCRIPT", SCRIPT)
    template = template.replace("START_CHUNK", START_CHUNK)
    template = template.replace("END_CHUNK", END_CHUNK)
    template = template.replace("TIME", get_time(submission_args.time))
    template = template.replace("NAME", NAME)
    template = template.replace("NUM_GPUS", NUM_GPUS)
    template = template.replace("PARALLEL", PARALLEL)
    template = template.replace("ACCOUNT", submission_args.account)
    template = template.replace("PYTHON_ENV_STR", PYTHON_ENV_STR)
    template = template.replace("GPU_TYPE", GPU_TYPE)
    slurm_script = f"slurm/{NAME}.sh"

    with open(slurm_script, "w+") as f:
        f.write(template)

    tqdm.write(f"File move command: {file_move_command}")
    tqdm.write(f"Launch command: {launch_command}")
    tqdm.write(f"Script:\n{SCRIPT}")
    tqdm.write(f"SLURM submission script written to {slurm_script}")
    os.system(f"sbatch {slurm_script}")
