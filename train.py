#! /usr/bin/env python

import tensorflow as tf
import numpy as np
import os
import time
import datetime
import data_helpers
from text_cnn import TextCNN
from tensorflow.contrib import learn

# Parameters
# ==================================================
checkpoint_directory = "baseline_rand"
embedding = ""
embedding_dim = 300
filter_sizes = [3,4,5]
num_filters = 128
num_channels = 1

evaluate_every = 100
checkpoint_every = 100
num_checkpoints = 5

dropout_keep_prob = 0.5
l2_reg_lambda = 0.0
batch_size = 64
num_epochs = 100

best_accuracy = 0

def preprocess():
    # Data Preparation
    # ==================================================

    # Load data
    print("Loading data...")
    # x_text, y = data_helpers.load_data_and_labels(positive_data_file, negative_data_file)
    x_train, y_train = data_helpers.load_sst_fine('./data/sst-fine/stsa.fine.train')
    x_dev, y_dev = data_helpers.load_sst_fine('./data/sst-fine/stsa.fine.test')
    # Build vocabulary
    max_document_length = max([len(x.split(" ")) for x in x_train])
    vocab_processor = learn.preprocessing.VocabularyProcessor(max_document_length)
    x_train = np.array(list(vocab_processor.fit_transform(x_train)))
    x_dev = np.array(list(vocab_processor.fit_transform(x_dev)))

    # Randomly shuffle data
    # np.random.seed(10)
    # shuffle_indices = np.random.permutation(np.arange(len(y)))
    # x_shuffled = x[shuffle_indices]
    # y_shuffled = y[shuffle_indices]

    # Split train/test set
    # TODO: This is very crude, should use cross-validation
    # dev_sample_index = -1 * int(dev_sample_percentage * float(len(y)))
    # x_train, x_dev = x_shuffled[:dev_sample_index], x_shuffled[dev_sample_index:]
    # y_train, y_dev = y_shuffled[:dev_sample_index], y_shuffled[dev_sample_index:]

    # del x, y, x_shuffled, y_shuffled

    print("Vocabulary Size: {:d}".format(len(vocab_processor.vocabulary_)))
    print("Train/Dev split: {:d}/{:d}".format(len(y_train), len(y_dev)))
    return x_train, y_train, vocab_processor, x_dev, y_dev

def train(x_train, y_train, vocab_processor, x_dev, y_dev):
    # Training
    # ==================================================

    with tf.Graph().as_default():
        session_conf = tf.ConfigProto(
          allow_soft_placement=True,
          log_device_placement=False)
        sess = tf.Session(config=session_conf)
        with sess.as_default():
            cnn = TextCNN(
                sequence_length=x_train.shape[1],
                num_classes=y_train.shape[1],
                vocab_size=len(vocab_processor.vocabulary_),
                embedding_size=embedding_dim,
                filter_sizes=filter_sizes,
                num_filters=num_filters,
                l2_reg_lambda=l2_reg_lambda,
                num_channels=num_channels)

            # Define Training procedure
            global_step = tf.Variable(0, name="global_step", trainable=False)
            optimizer = tf.train.AdamOptimizer(1e-3)
            grads_and_vars = optimizer.compute_gradients(cnn.loss)
            train_op = optimizer.apply_gradients(grads_and_vars, global_step=global_step)

            # Keep track of gradient values and sparsity (optional)
            grad_summaries = []
            for g, v in grads_and_vars:
                if g is not None:
                    grad_hist_summary = tf.summary.histogram("{}/grad/hist".format(v.name), g)
                    sparsity_summary = tf.summary.scalar("{}/grad/sparsity".format(v.name), tf.nn.zero_fraction(g))
                    grad_summaries.append(grad_hist_summary)
                    grad_summaries.append(sparsity_summary)
            grad_summaries_merged = tf.summary.merge(grad_summaries)

            # Output directory for models and summaries
            #timestamp = str(int(time.time()))
            out_dir = os.path.abspath(os.path.join(os.path.curdir, "runs-fine", checkpoint_directory))
            print("Writing to {}\n".format(out_dir))

            # Summaries for loss and accuracy
            loss_summary = tf.summary.scalar("loss", cnn.loss)
            acc_summary = tf.summary.scalar("accuracy", cnn.accuracy)

            # Train Summaries
            train_summary_op = tf.summary.merge([loss_summary, acc_summary, grad_summaries_merged])
            train_summary_dir = os.path.join(out_dir, "summaries", "train")
            train_summary_writer = tf.summary.FileWriter(train_summary_dir, sess.graph)

            # Dev summaries
            dev_summary_op = tf.summary.merge([loss_summary, acc_summary])
            dev_summary_dir = os.path.join(out_dir, "summaries", "dev")
            dev_summary_writer = tf.summary.FileWriter(dev_summary_dir, sess.graph)

            # Checkpoint directory. Tensorflow assumes this directory already exists so we need to create it
            checkpoint_dir = os.path.abspath(os.path.join(out_dir, "checkpoints"))
            checkpoint_prefix = os.path.join(checkpoint_dir, "model")
            if not os.path.exists(checkpoint_dir):
                os.makedirs(checkpoint_dir)
            saver = tf.train.Saver(tf.all_variables())

            # Write vocabulary
            vocab_processor.save(os.path.join(out_dir, "vocab"))

            # Initialize all variables
            sess.run(tf.initialize_all_variables())

            #Load pre-trained word vector.
            if embedding != "None":
                # initial matrix with random uniform
                initW = np.random.uniform(-0.25,0.25,(len(vocab_processor.vocabulary_), embedding_dim))

                if embedding == "word2vec":                   
                    # load any vectors from the word2vec
                    print("Embed word using {}\n".format(embedding))
                    with open("./embedding/GoogleNews-vectors-negative300.bin", "rb") as f:
                        header = f.readline()
                        vocab_size, layer1_size = map(int, header.split())  # 3000000, 300
                        binary_len = np.dtype('float32').itemsize * layer1_size # 1200
                        for line in range(vocab_size):
                            word = []
                            while True:
                                ch = f.read(1).decode('latin-1')
                                if ch == ' ':
                                    word = ''.join(word)
                                    break
                                if ch != '\n':
                                    word.append(ch)
                                else:
                                    print('else: ', word, ch)
                            idx = vocab_processor.vocabulary_.get(word)
                            if idx != 0:
                                initW[idx] = np.fromstring(f.read(binary_len), dtype='float32')
                            else:
                                f.read(binary_len)

                if embedding == "glove":
                    # load any vectors from the glove
                    print("Embed word using {}\n".format(embedding))
                    with open("./embedding/glove.6B.300d.txt", "rb") as f:
                        while True:
                            line = f.readline()
                            if not line: break
                            line = line.decode().split(" ")
                            word = line[0]
                            idx = vocab_processor.vocabulary_.get(word)
                            if idx != 0:
                                initW[idx] = np.array(line[1:], dtype='float32')

                if embedding == "fasttext":
                    # load any vectors from the fasttext
                    print("Embed word using {}\n".format(embedding))
                    with open("./embedding/fasttext-300d-1M-subword.vec", "rb") as f:
                        header = f.readline()
                        vocab_size, layer1_size = map(int, header.split())  # 3000000, 300
                        for line in range(vocab_size):
                            line = f.readline()
                            if not line: break
                            line = line.decode().split(" ")
                            word = line[0]
                            idx = vocab_processor.vocabulary_.get(word)
                            if idx != 0:
                                initW[idx] = np.array(line[1:], dtype='float32')

                sess.run(cnn.W.assign(initW))
                if num_channels ==2:
                    sess.run(cnn.W2.assign(initW))
                print("Ended")
            #finished loading pre-trained word vector.

            def train_step(x_batch, y_batch):
                """
                A single training step
                """
                feed_dict = {
                  cnn.input_x: x_batch,
                  cnn.input_y: y_batch,
                  cnn.dropout_keep_prob: dropout_keep_prob
                }
                _, step, summaries, loss, accuracy = sess.run(
                    [train_op, global_step, train_summary_op, cnn.loss, cnn.accuracy],
                    feed_dict)
                time_str = datetime.datetime.now().isoformat()
                print("{}: step {}, loss {:g}, acc {:g}".format(time_str, step, loss, accuracy))
                train_summary_writer.add_summary(summaries, step)

            def dev_step(x_batch, y_batch, writer=None):
                """
                Evaluates model on a dev set
                """
                feed_dict = {
                  cnn.input_x: x_batch,
                  cnn.input_y: y_batch,
                  cnn.dropout_keep_prob: 1.0
                }
                step, summaries, loss, accuracy = sess.run(
                    [global_step, dev_summary_op, cnn.loss, cnn.accuracy],
                    feed_dict)
                time_str = datetime.datetime.now().isoformat()
                print("{}: step {}, loss {:g}, acc {:g}".format(time_str, step, loss, accuracy))
                best_accuracy = max(accuracy, best_accuracy)
                if writer:
                    writer.add_summary(summaries, step)

            # Generate batches
            batches = data_helpers.batch_iter(
                list(zip(x_train, y_train)), batch_size, num_epochs)
            # Training loop. For each batch...
            for batch in batches:
                x_batch, y_batch = zip(*batch)
                train_step(x_batch, y_batch)
                current_step = tf.train.global_step(sess, global_step)
                if current_step % evaluate_every == 0:
                    print("\nEvaluation:")
                    dev_step(x_dev, y_dev, writer=dev_summary_writer)
                    print("")
                if current_step % checkpoint_every == 0:
                    path = saver.save(sess, checkpoint_prefix, global_step=current_step)
                    print("Saved model checkpoint to {}\n".format(path))

def main():
    x_train, y_train, vocab_processor, x_dev, y_dev = preprocess()
    train(x_train, y_train, vocab_processor, x_dev, y_dev)
    print("============ best accuracy ============")
    print(best_accuracy)

main()
