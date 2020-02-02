import sys
import os
import numpy as np
import matplotlib.pyplot as plt

from train_dataset_classifier import load_datasets_processed
from sklearn.cluster import KMeans
from sklearn.manifold import TSNE
from sklearn.decomposition import PCA
from sklearn.preprocessing import minmax_scale


def _plot_clusters(data, colors, cluster_labels, labels, ax_handle, annotate=False):
    for i, color in enumerate(colors):
        indices = np.where(cluster_labels == labels[i])
        X = data[indices]
        ax_handle.scatter(X[:, 0], X[:, 1], color=color, label=labels[i])
        if annotate:
            offset = np.random.uniform(-0.1, 0.1)
            while np.isclose(offset, 0, rtol=1e-02):
                offset = np.random.uniform(-0.1, 0.1)
            # simply annotate the first sample
            ax_handle.annotate(labels[i], (X[0, 0]+offset, X[0, 1]+offset), color=color)
    return ax_handle


cfg = {}
annotate = True
meta_features_path = '/home/autodl/processed_datasets/1e4_meta'
#meta_features_path = '/home/autodl/processed_datasets/1e4_combined'

cfg['proc_dataset_dir'] = meta_features_path
cfg["datasets"] = ['Chucky', 'Decal', 'Hammer', 'Hmdb51', 'Katze', 'Kreatur', 'Munster', 'Pedro', 'SMv2', 'Ucf101',
                         'binary_alpha_digits', 'caltech101', 'caltech_birds2010', 'caltech_birds2011', 'cats_vs_dogs', 'cifar100',
                         'cifar10', 'coil100', 'colorectal_histology', 'deep_weeds', 'emnist', 'eurosat', 'fashion_mnist',
                         'horses_or_humans', 'kmnist', 'mnist', 'oxford_flowers102']

n_samples_to_use = 10000
dataset_list = load_datasets_processed(cfg, cfg["datasets"])
n_clusters = len(dataset_list)
print("{} datasets loaded".format(n_clusters))

X_train = [ds[0].dataset[:n_samples_to_use].numpy() for ds in dataset_list]  # 0 -> for now, only use train data for clustering
n_feature_dimensions = X_train[0].shape[1]
X_train = np.concatenate(X_train, axis=0)
X_labels = [ds[2] for ds in dataset_list]

#X_test = [ds[1].dataset.numpy() for ds in dataset_list]
#X_test = np.concatenate(X_test, axis=0)

""" normalization (for now: only scale to [0,1] to preserve shape and outliers) """
X_train = minmax_scale(X_train, axis=0)  # axis=0 -> scale each feature independently (not sample)

""" fit k-means clustering """
kmeans_estimator = KMeans(n_clusters=n_clusters, random_state=0, n_jobs=4).fit(X_train)

""" predict the cluster index for each sample """
X_indices = kmeans_estimator.predict(X_train)
X_labels_cluster_order = np.asarray([X_labels[i] for i in X_indices])

X_labels_unique, idx = np.unique(X_labels_cluster_order, return_index=True)
X_labels_unique = X_labels_unique[np.argsort(idx)]

""" reduce dimensionality of original data for plotting """
X_train_tsne_embedding = TSNE(n_components=2).fit_transform(X_train)
X_train_pca_embedding = PCA(n_components=2).fit_transform(X_train)

""" assign the cluster indices to dim-reduced data """
fig = plt.figure(figsize=(12, 12))
colors = plt.cm.rainbow(np.linspace(0, 1, len(X_labels_unique)))

ax1 = plt.subplot(211)
ax1 = _plot_clusters(data=X_train_tsne_embedding, colors=colors, cluster_labels=X_labels_cluster_order, labels=X_labels_unique, ax_handle=ax1, annotate=annotate)
ax1.legend(prop={'size': 7}, loc="upper right")
ax1.title.set_text("t-SNE")

ax2 = plt.subplot(212)
ax2 = _plot_clusters(data=X_train_pca_embedding, colors=colors, cluster_labels=X_labels_cluster_order, labels=X_labels_unique, ax_handle=ax2, annotate=annotate)
ax2.title.set_text("PCA")
ax2.legend(prop={'size': 7}, loc="upper right")

plot_title = "Datasets clustered with k-means ({}-dim. meta-features, {} samples per dataset)".format(n_feature_dimensions, n_samples_to_use)
fig.suptitle(plot_title, fontsize=14)
file_path = os.path.join(meta_features_path, "cluster_{}_samples.png".format(n_samples_to_use))
plt.savefig(file_path)
print("file saved to {}".format(file_path))
plt.show()


