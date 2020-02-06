# AutoDLComp19
AutoDL Competition 2019


## Installation

Activate a conda python3.5 environment then run
```bash
bash install/requirements_gcc.sh
pip install -r install/requirements.txt
bash install/install_torch.sh
bash install/install_precommit.sh
bash install/install_just.sh
```


## Usage


### Running locally

To run the competition evaluation locally run
```bash
python competition/run_local_test.py \
    --dataset_dir datasets/DATASET \
    --code_dir MODELY_PY_FOLDER \
    --job_id JOB_ID \
    --task_id TASK_ID

# E.g.,
python competition/run_local_test.py \
    --dataset_dir datasets/public_data/Chucky \
    --code_dir competition/sample_submission \
    --job_id [SOME_INTEGER] \
    --task_id [SOME_INTEGER]
```

If you want to overwrite the output dir (for repeated local testing for example), supply the `--overwrite` flag.

If you want to open an interactive job session on the cluster run from the login node:
```bash
srun -p meta_gpu-x --pty bash
```
Then you can activate your environment and run the above scripts.

The script `submission/meta_cluster_array_job.sh` provides an examplefor running an array job. On the login node run:
```bash
sbatch submission/meta_cluster_array_job.sh
```


### Making a submission

To create a submission `.zip` for the codalab platform run

```bash
python submission/competition.py
```

This uses the settings in `src/config.hjson` to determine the modality, lookup paths, finetuning strategy, pretrained_parameters and model to load, hyperparameters, etc. To change the settings, you can either edit `src/config.hjson` or via arguments:


```bash
python submission/competition.py --lr 1e-4
```

You need to specify which model parameter files you want to include in the submission. You can do this via editing the `active_model_files` attribute, e.g.,

```json
active_model_files: ["resnet18-5c106cde"]  # With respect to model_dir
```

To include a python package that is not included on the competition platform, edit the `extra_packages` attribute, e.g.,

```json
extra_packages: [".miniconda/envs/autodl/lib/python3.5/site-packages/hjson"]
```


### Do not run pre-commit hooks

To commit without runnning `pre-commit` use `git commit --no-verify -m <COMMIT MESSAGE>`.


## Project Structure

```
├── experiments/                           <<  Logs and other files generated during runtime
│
├── install/                               <<  Requirements and scripts for installation
│
├── src/                                   <<  Source code
│   └── competition/                       <<  Competition source code
│       ├── ingestion_program/             <<  Main execution library
│       ├── scoring_program/               <<  Source code to produce AUL score
│       └── run_local_test.py              <<  Execute competition evaluation locally
│
└── submission/                            <<  Submission utilities
    └── competition.py                     <<  Automatic generation of competition submissions
```


## License

[Apache 2.0](LICENSE)
