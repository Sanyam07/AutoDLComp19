from pathlib import Path

import yaml


def get_available_dataset_names(valid_keys, selected_train_datasets=None, no_augmented=False):
    """
    Produces two lists of dataset names, one containing training and the other containing
    validation dataset names. Path to the datasets directory must be specified through
    src/configs/default.yaml (cluster_datasets_dir key).
    Parameters:
      valid_keys - A list of strings. Each string indicates which dataset will be placed in the
      returned valid dataset list.
      selected_train_datasets - A list of strings. Each string represents a dataset that is supposed
      to be searched for and if it exists, the respective datasets are returned in the training
      dataset list.
      no_augmented - Flag indicating whether only non-augmented datasets ending with the keyword
      '_original' should be returned.
    """
    # Read the default config
    configs_path = Path("src/configs/")
    default_config_path = configs_path / "default.yaml"

    with default_config_path.open() as in_stream:
        default_config = yaml.safe_load(in_stream)

    cluster_datasets_dir = Path(default_config["cluster_datasets_dir"])
    all_datasets = [path.name for path in cluster_datasets_dir.glob("*") if path.is_dir()]

    if no_augmented:
        all_datasets = [dataset for dataset in all_datasets if dataset.endswith("_original")]

    val_datasets = [dataset for dataset in all_datasets for key in valid_keys if key in dataset]
    train_datasets = [dataset for dataset in all_datasets if dataset not in val_datasets]

    if selected_train_datasets:
        train_datasets = [
            dataset for dataset in train_datasets
            for key in selected_train_datasets if dataset.startswith(key) and key + "_" in dataset
        ]

    return train_datasets, val_datasets


train_keys = [
    "cifar100",  # objects
    "cifar10",  # objects
    "mnist",  # handwritten digits, replacement for Munster
    "colorectal_histology",  # colorectal cancer
    "caltech_birds2010",  # birds
    "eurosat",  # satellite images
    "cars196",  # replacement for Hammer
    "visual_domain_decathlon_dtd",  # textures
    "imagenette",  # subset of imagenet
    "malaria",  # cell images
    "svhn_cropped",  # house numbers
    "uc_merced",  # urban area imagery
    "visual_domain_decathlon_daimlerpedcls",  # pedestrians
    "oxford_flowers102",  # flowers
    "fashion_mnist",  # fashion articles
    "citrus_leaves",  # citrus fruits and leaves
    "cycle_gan_summer2winter_yosemite",  # landscape
    "cycle_gan_facades",  # facades
    "horses_or_humans",  # sprites
    "visual_domain_decathlon_ucf101"  # youtube action
]

valid_keys = ["coil100", "kmnist", "vgg-flowers", "oxford_iiit_pet", "cmaterdb_telugu"]
train_datasets, val_datasets = get_available_dataset_names(
    valid_keys=valid_keys, selected_train_datasets=train_keys, no_augmented=True
)
all_datasets = train_datasets + val_datasets
