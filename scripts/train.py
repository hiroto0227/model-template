import argparse
import os, sys
import traceback
import numpy as np
from datetime import datetime
from tqdm import tqdm
import time
import torch
import torchtext
from torchtext.data import BucketIterator, Iterator
from torch import optim
import torch.nn as nn
import torch.nn.functional as F
from dataset import ChemdnerDataset
from model.lstm_crf import LSTMCRFTagger
from model.attention_lstm import Att_LSTM
from evaluate import evaluate
import pandas as pd


def checkpoint(epoch, model, model_path, interrupted=False):
    print('model saved!!')
    if interrupted:
        torch.save(model.state_dict(), MODEL_PATH + '_{}ep_{}bs_interrupted.pth'.format(epoch, opt.batch_size))
    else:
        torch.save(model.state_dict(), MODEL_PATH + '_{}ep_{}bs.pth'.format(epoch, opt.batch_size))
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='deep image inpainting')
    parser.add_argument('--batch_size', type=int, default=50, help='training batch size')
    parser.add_argument('--epoch', type=int, default=1, help='training epoch')
    parser.add_argument('--use_cpu', type=bool, default=True, help='training epoch')
    opt = parser.parse_args()

    if torch.cuda.is_available() and opt.use_cpu:
        print('============ use GPU ==============')
        CUDA_FLAG = True

    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    MODEL_PATH = os.path.join(CURRENT_DIR, '../models/', 'bilstm_crf_{}_{}bs'.format(datetime.now().strftime("%Y%m%d%H%M"), opt.batch_size))
    RESULT_PATH = os.path.join(CURRENT_DIR, '../results/')
    train_dataset = ChemdnerDataset(path=os.path.join(CURRENT_DIR, '../datas/processed/train.csv'))
    token2id, label2id = train_dataset.make_vocab()
    id2label = [k for k, v in label2id.items()]
    valid_dataset = ChemdnerDataset(path=os.path.join(CURRENT_DIR, '../datas/processed/test.csv'))

    model = LSTMCRFTagger(vocab_dim=len(token2id), tag_dim=len(label2id), batch_size=opt.batch_size)

    if CUDA_FLAG:
        model.cuda()
    optimizer = optim.SGD(model.parameters(), lr=0.1, weight_decay=1e-4)

    loss_sum = 0
    train_iter = BucketIterator(train_dataset, batch_size=opt.batch_size, shuffle=True, repeat=False)
    df_epoch_results = pd.DataFrame(columns=['epoch', 'loss', 'valid_precision', 'valid_recall', 'valid_fscore', 'time'])

    for epoch in range(opt.epoch):
        start = time.time()
        loss_per_epoch = 0
        for batch_i, batch in tqdm(enumerate(train_iter)):
            try:
                batch_start = time.time()
                model.zero_grad()
                model.train()
                ###### LSTM ##########
                # print('\ninput: {}'.format(batch.text.shape)) # (seq_length, batch_size)
                #output = model(batch.text.cpu()) # (seq_length, batch_size, tag_size)
                # print('output: {}'.format(output.shape))
                # loss = F.nll_loss(output.view(-1, len(label2id)), batch.label.view(-1).cpu())
                ####### BiLSTM CRF ########
                if CUDA_FLAG:
                    loss = -1 * model(batch.text.cuda(), batch.label.cuda())
                else:
                    loss = -1 * model(batch.text.cpu(), batch.label.cpu())
                print('loss: {}'.format(float(loss)))
                loss.backward()
                optimizer.step()
                loss_per_epoch += float(loss)
            except:
                checkpoint(epoch, model, MODEL_PATH, interrupted=True)
                traceback.print_exc()
                sys.exit(1)
        precision, recall, f1_score = evaluate(dataset=valid_dataset, model=model, batch_size=opt.batch_size, text_field=train_dataset.text_field, label_field=train_dataset.label_field, id2label=id2label, verbose=0)
        print('{}epoch\nloss: {}\nvalid: {}\ntime: {} sec.\n'.format(epoch + 1, loss_per_epoch, f1_score, time.time() - start))
        df_epoch_results = df_epoch_results.append(pd.Series({'epoch': epoch + 1, 'loss': loss_per_epoch, 'valid_precision': precision, 'valid_recall': recall, 'valid_fscore': f1_score, 'time': time.time() - start}), ignore_index=True)
    checkpoint(epoch, model, MODEL_PATH)
    df_epoch_results.to_csv(os.path.join(RESULT_PATH, 'result_epoch_{}.csv'.format(MODEL_PATH.split('/')[-1])), float_format='%.3f')
