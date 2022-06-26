import torch
from abc import ABCMeta, abstractmethod
import matplotlib.pyplot as plt
import numpy as np
import torch.nn.functional as F
import gzip
from torch import nn


def get_act_function(descr):
    if descr == "relu":
        return F.relu
    elif descr == "sigm":
        return F.sigmoid
    elif descr == "tanh":
        return F.tanh
    elif descr == "leaky":
        return F.leaky_relu
    else:
        raise NotImplementedError


def get_act_function_module(descr):
    if descr == "relu":
        return nn.ReLU()
    elif descr == "sigm":
        return nn.Sigmoid()
    elif descr == "tanh":
        return nn.Tanh()
    elif descr == "leaky":
        return nn.LeakyReLU()
    else:
        raise NotImplementedError


def save_to_npy_gz(array, filename):
    f = gzip.GzipFile(filename + ".npy.gz", "w")
    np.save(file=f, arr=array)
    f.close()


def load_to_npy_gz(filename):
    f = gzip.GzipFile(filename + ".npy.gz", "r")
    array = np.load(f)
    return array


def prepare_device(n_gpu_use, gpu_id=None):
    """
    setup specific GPU device if available, move model into configured device
    """
    n_gpu = torch.cuda.device_count()
    if n_gpu_use > 0 and n_gpu == 0:
        print("Warning: There\'s no GPU available on this machine,"
              "training will be performed on CPU.")
        n_gpu_use = 0
    if n_gpu_use > n_gpu:
        print("Warning: The number of GPU\'s configured to use is {}, but only {} are available "
              "on this machine.".format(n_gpu_use, n_gpu))
        n_gpu_use = n_gpu
    device = torch.device('cuda:{}'.format(gpu_id) if n_gpu_use > 0 else 'cpu')
    #    torch.cuda.device(device)
    print("Executing on device: ", device)
    return device


def matplotlib_imshow(img, one_channel=False):
    if one_channel:
        img = img.mean(dim=0)
    img = img / 2 + 0.5  # unnormalize
    npimg = img.numpy()
    if one_channel:
        plt.imshow(npimg, cmap="Greys")
    else:
        plt.imshow(np.transpose(npimg, (1, 2, 0)))


class Metric:
    def __init__(self):
        self.reset()

    @abstractmethod
    def reset(self):
        """
        Resets the metric to it's initial state.

        This is called at the start of each epoch.
        """
        pass

    @abstractmethod
    def update(self, output, target):
        """
        Updates the metric's state using the passed batch output.

        This is called once for each batch.

        Args:
            output: the is the output from the engine's process function.
            target: target to match
        """
        pass

    @abstractmethod
    def compute(self):
        """
        Computes the metric based on it's accumulated state.

        This is called at the end of each epoch.

        Returns:
            Any: the actual quantity of interest.

        Raises:
            NotComputableError: raised when the metric cannot be computed.
        """
        pass


class Accuracy(Metric):

    def __init__(self, is_multilabel=False, type=None):
        self._is_multilabel = is_multilabel
        self._type = type
        # self._num_classes = None
        self._num_correct = None
        self._num_examples = None
        self.best_accuracy = -1
        self.external_best_acc = -1
        super(Accuracy, self).__init__()

    def reset(self):
        # self._num_classes = None
        self._num_correct = 0
        self._num_examples = 0
        super(Accuracy, self).reset()

    def update(self, output, target, batch_compute=False, idx=None):
        y_pred = output

        if self._type == "binary":
            correct = torch.eq(y_pred.view(-1).to(target), target.view(-1))
        elif self._type == "multiclass":
            pred = y_pred.argmax(dim=1, keepdim=True)  # get the index of the max log-probability
            correct = pred.eq(target.view_as(pred))
            if batch_compute:
                batch_dim = correct.shape[0]
                batch_accuracy = torch.sum(correct).item() / batch_dim

        if self._type == "multilabel":
            # if y, y_pred shape is (N, C, ...) -> (N x ..., C)
            num_classes = y_pred.size(1)
            last_dim = y_pred.ndimension()
            y_pred = torch.transpose(y_pred, 1, last_dim - 1).reshape(-1, num_classes)
            target = torch.transpose(target, 1, last_dim - 1).reshape(-1, num_classes)
            correct = torch.all(target == y_pred.type_as(target), dim=-1)
        elif self._type == "semisupervised":
            target = target[idx]
            y_pred = y_pred[idx]
            pred = y_pred.argmax(dim=1, keepdim=True)  # get the index of the max log-probability
            correct = pred.eq(target.view_as(pred))

        # elif self._type == "semisupervised":
        #     output[data.idx_test], data.targets[data.idx_test]
        self._num_correct += torch.sum(correct).item()
        self._num_examples += correct.shape[0]

        if batch_compute:
            return batch_accuracy

    def get_best(self):
        return self.best_accuracy

    def compute(self):
        if self._num_examples == 0:
            raise Exception('Accuracy must have at least one example before it can be computed.')
        acc = self._num_correct / self._num_examples
        if acc > self.best_accuracy:
            self.best_accuracy = acc
        return self._num_correct / self._num_examples


def get_markdown_description(description_json, exp_id):
    markdown = f"# Experiment {exp_id}\n\n"
    description_md = description_json.replace("\n", "<br>").replace(" ", "&nbsp;")
    description_md = description_md.replace("[", "\\[").replace("]", "\\]")

    return markdown + description_md


def dict_to_md(dict_input, vis_size=10):
    """
    inspired from https://github.com/codazoda/tomark/blob/master/tomark/tomark.py
    :param dict_input:
    :return:
    """

    from itertools import islice
    def get_chunk(input, size):
        it = iter(input)
        for i in range(0, len(input), size):
            yield {k: input[k] for k in islice(it, size)}

    markdowntables = []

    for item in get_chunk(dict_input, 10):
        markdowntable = ""
        # Make a string of all the keys in the first dict with pipes before after and between each key
        markdownheader = '| ' + ' | '.join(map(str, item.keys())) + ' |'
        # Make a header separator line with dashes instead of key names
        markdownheaderseparator = '|-----' * len(item.keys()) + '|'
        # Add the header row and separator to the table
        markdowntable += markdownheader + '\n'
        markdowntable += markdownheaderseparator + '\n'
        # Loop through the list of dictionaries outputting the rows
        markdownrow = ""
        for key, col in item.items():
            markdownrow += '| ' + str(col) + ' '
        markdowntable += markdownrow + '|' + '\n'
        markdowntables.append(markdowntable)

    return markdowntables
