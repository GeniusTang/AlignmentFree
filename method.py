from src._count import kmer_count
from src._count import kmer_count_m_k
from scipy.spatial.distance import cosine
from sklearn.metrics.pairwise import cosine_similarity
from scipy import stats
from functools import partial
import numpy as np
import os
import pickle
from numpy import linalg as LA

Suffix = ['fna', 'fa', 'fasta']
Alphabeta = ['A', 'C', 'G', 'T']
Alpha_dict = dict(zip(Alphabeta, range(4)))

def rev_comp(num, K):
    nuc_rc = 0
    for i in range(K):
        shift = 2 * (K-i-1)
        nuc_rc += (3 - (num>>shift)&3) * (4**i)
    return nuc_rc

def rev_count(count, K):
    new_count = np.zeros_like(count)
    for i in range(4**K):
        rev = rev_comp(i, K)
        new_count[i] = count[i] + count[rev]
    return new_count

def count_pickle(seqfile, K, Reverse, P_dir):
    seq_count_p = os.path.join(P_dir, os.path.basename(seqfile) + '.%s_%d_cnt.p'%('R' if Reverse else 'NR', K))
    return seq_count_p


def get_K(seqfile, K, Num_Threads, Reverse, P_dir):
    seq_count_K_p = count_pickle(seqfile, K, Reverse, P_dir)
    if os.path.exists(seq_count_K_p):
        with open(seq_count_K_p, 'rb') as f:
            K_count = pickle.load(f)
    else:
        if K>= 6:
            K_count = np.copy(kmer_count(seqfile, K, Num_Threads, Reverse))
        else:
            K_count = np.copy(kmer_count(seqfile, K, Num_Threads, False))
            K_count = rev_count(K_count, K)
        with open(seq_count_K_p, 'wb') as f:
            pickle.dump(K_count, f, pickle.HIGHEST_PROTOCOL)
    return K_count

def get_M_K(seqfile, M, K, Num_Threads, Reverse, P_dir):
    seq_count_M_p = count_pickle(seqfile, M, Reverse, P_dir)
    seq_count_K_p = count_pickle(seqfile, K, Reverse, P_dir)
    if os.path.exists(seq_count_M_p) and os.path.exists(seq_count_K_p):
        with open(seq_count_M_p, 'rb') as f:
            M_count = pickle.load(f)
        with open(seq_count_K_p, 'rb') as f:
            K_count = pickle.load(f)
    else:
        print('Counting kmers of %s.'%seqfile)
        if not Reverse or M>=6:
            count = np.copy(kmer_count_m_k(seqfile, M, K, Num_Threads, Reverse))
            M_count = count[:4**M]
            K_count = count[4**M:]
        else:
            M_count = np.copy(kmer_count(seqfile, M, Num_Threads, False))
            M_count = rev_count(M_count, M)
            if K>= 6:
                K_count = np.copy(kmer_count(seqfile, K, Num_Threads, Reverse))
            else:
                K_count = np.copy(kmer_count(seqfile, K, Num_Threads, False))
                K_count = rev_count(K_count, K)
        with open(seq_count_M_p, 'wb') as f:
            pickle.dump(M_count, f, pickle.HIGHEST_PROTOCOL)
        with open(seq_count_K_p, 'wb') as f:
            pickle.dump(K_count, f, pickle.HIGHEST_PROTOCOL)
    return M_count, K_count

def get_transition(count_array):
    shape = len(count_array)
    transition_array = count_array.reshape(shape//4, 4)
    with np.errstate(divide='ignore', invalid='ignore'):
        transition_array = (transition_array / np.sum(transition_array, 1)[:, np.newaxis])
        transition_array[np.isnan(transition_array)] = 0
    return transition_array

def get_expect(seqfile, M, K, Num_Threads, Reverse, P_dir):
    M_count, K_count = get_M_K(seqfile, M, K, Num_Threads, Reverse, P_dir)
    seqfile_e_p = os.path.join(P_dir, os.path.basename(seqfile) + '.%s_M%d_K%d_e.p'%('R' if Reverse else 'NR', M-1, K))
    if os.path.exists(seqfile_e_p):
        with open(seqfile_e_p, "rb") as f:
            expect = pickle.load(f)
    else:
        trans = get_transition(M_count)
        expect = M_count
        for _ in range(K-M):
            trans = np.tile(trans, (4, 1))
            expect = (expect[:,np.newaxis] * trans).flatten()
        with open(seqfile_e_p, "wb") as f:
            pickle.dump(expect, f, pickle.HIGHEST_PROTOCOL)
    return K_count, expect

def get_expect_reverse(seqfile, M, K, Num_Threads, P_dir):
    a_M_count, a_K_count = get_M_K(seqfile, M, K, Num_Threads, False, P_dir)
    b_M_count, b_K_count = get_M_K(seqfile, M, K, Num_Threads, True, P_dir)
    M_count = b_M_count - a_M_count
    del a_M_count
    del b_M_count
    K_count = b_K_count - a_K_count
    del a_K_count
    del b_K_count
    trans = get_transition(M_count)
    expect = M_count
    for _ in range(K-M):
        trans = np.tile(trans, (4, 1))
        expect = (expect[:,np.newaxis] * trans).flatten()
    return K_count, expect

def get_d2star_f(seqfile, M, K, Num_Threads, Reverse, P_dir):
    seqfile_f_p = os.path.join(P_dir, os.path.basename(seqfile) + '.%s_M%d_K%d_d2star_f.p'%('R' if Reverse else 'NR', M-1, K))
    if os.path.exists(seqfile_f_p):
        with open(seqfile_f_p, "rb") as f:
            d2star_f = pickle.load(f)
    else:
        K_count, expect = get_expect(seqfile, M, K, Num_Threads, Reverse, P_dir)
        with np.errstate(divide='ignore', invalid='ignore'):
            d2star_f = (K_count-expect)/np.sqrt(expect)
            d2star_f[np.isnan(d2star_f)]=0
        with open(seqfile_f_p, "wb") as f:
            pickle.dump(d2star_f, f, pickle.HIGHEST_PROTOCOL)
    return d2star_f

def get_d2star_all_f(sequence_list, M, K, Num_Threads, Reverse, P_dir):
    f_matrix = np.ones((len(sequence_list), 4**K))
    for i, seqfile in enumerate(sequence_list):
        f_matrix[i] = get_d2star_f(seqfile, M, K, Num_Threads, Reverse, P_dir)
    return f_matrix

def get_CVTree_f(seqfile, M, K, Num_Threads, Reverse, P_dir):
    seqfile_f_p = os.path.join(P_dir, os.path.basename(seqfile) + '.%s_M%d_K%d_CVTree_f.p'%('R' if Reverse else 'NR', M-1, K))
    if os.path.exists(seqfile_f_p):
        with open(seqfile_f_p, "rb") as f:
            CVTree_f = pickle.load(f)
    else:
        K_count, expect = get_expect(seqfile, M, K, Num_Threads, Reverse, P_dir)
        with np.errstate(divide='ignore', invalid='ignore'):
            CVTree_f = (K_count-expect)/expect
            CVTree_f[np.isnan(CVTree_f)]=0
        with open(seqfile_f_p, "wb") as f:
            pickle.dump(CVTree_f, f, pickle.HIGHEST_PROTOCOL)
    return CVTree_f   

def get_all_K(sequence_list, M, K, Num_Threads, Reverse, P_dir):
    K_matrix = np.ones((len(sequence_list), 4**K))
    for i, seqfile in enumerate(sequence_list):
        M_count, K_count = get_M_K(seqfile, M, K, Num_Threads, Reverse, P_dir)
        K_matrix[i] = K_count/np.sum(K_count)
    return K_matrix

def Ma(seqfile_1, seqfile_2, M, K, Num_Threads, Reverse, P_dir):
    a_K = get_K(seqfile_1, K, Num_Threads, Reverse, P_dir)    
    b_K = get_K(seqfile_2, K, Num_Threads, Reverse, P_dir)    
    diff = a_K/np.sum(a_K) - b_K/np.sum(b_K)
    return LA.norm(diff, 1) 

def Eu(seqfile_1, seqfile_2, M, K, Num_Threads, Reverse, P_dir):
    a_K = get_K(seqfile_1, K, Num_Threads, Reverse, P_dir)
    b_K = get_K(seqfile_2, K, Num_Threads, Reverse, P_dir)
    diff = a_K/np.sum(a_K) - b_K/np.sum(b_K)
    return LA.norm(diff)

def d2(seqfile_1, seqfile_2, M, K, Num_Threads, Reverse, P_dir):
    a_K = get_K(seqfile_1, K, Num_Threads, Reverse, P_dir)
    b_K = get_K(seqfile_2, K, Num_Threads, Reverse, P_dir)
    return 0.5 * cosine(a_K/np.sum(a_K), b_K/np.sum(b_K))

def d2star(seqfile_1, seqfile_2, M, K, Num_Threads, Reverse, P_dir):
    a_f = get_d2star_f(seqfile_1, M, K, Num_Threads, Reverse, P_dir)
    b_f = get_d2star_f(seqfile_2, M, K, Num_Threads, Reverse, P_dir)
    return 0.5 * cosine(a_f, b_f)

def CVTree(seqfile_1, seqfile_2, M, K, Num_Threads, Reverse, P_dir):
    a_f = get_CVTree_f(seqfile_1, M, K, Num_Threads, Reverse, P_dir)
    b_f = get_CVTree_f(seqfile_2, M, K, Num_Threads, Reverse, P_dir)
    return 0.5 * cosine(a_f, b_f)

def d2shepp(seqfile_1, seqfile_2, M, K, Num_Threads, Reverse, P_dir):
    a_K_count, a_expect = get_expect(seqfile_1, M, K, Num_Threads, Reverse, P_dir)
    a_diff = a_K_count - a_expect
    del a_K_count
    del a_expect
    b_K_count, b_expect = get_expect(seqfile_2, M, K, Num_Threads, Reverse, P_dir)
    b_diff = b_K_count - b_expect
    del b_K_count
    del b_expect
    denom = np.power(a_diff**2 + b_diff**2, 0.25)
    with np.errstate(divide='ignore', invalid='ignore'):
        a_f = a_diff/denom
        a_f[np.isnan(a_f)]=0
        b_f = b_diff/denom
        b_f[np.isnan(b_f)]=0 
    return 0.5 * cosine(a_f, b_f)

def d2shepp_error(seqfile, M, K, Num_Threads, P_dir):
    a_K_count, a_expect = get_expect(seqfile, M, K, Num_Threads, False, P_dir)
    a_diff = a_K_count - a_expect
    del a_K_count
    del a_expect
    b_K_count, b_expect = get_expect_reverse(seqfile, M, K, Num_Threads, P_dir)
    b_diff = b_K_count - b_expect
    del b_K_count
    del b_expect
    denom = np.power(a_diff**2 + b_diff**2, 0.25)
    with np.errstate(divide='ignore', invalid='ignore'):
        a_f = a_diff/denom
        a_f[np.isnan(a_f)]=0
        b_f = b_diff/denom
        b_f[np.isnan(b_f)]=0
    return 0.5 * cosine(a_f, b_f)

def d2star_matrix(f1_matrix, f2_matrix):
    d2star_matrix = 0.5 * (1 - cosine_similarity(f1_matrix, f2_matrix))
    np.fill_diagonal(d2star_matrix, 0)
    return d2star_matrix

def dist_matrix_pairwise(sequence_list, M, K, Num_Threads, Reverse, P_dir, method):
    N = len(sequence_list)
    matrix = np.zeros((N, N))
    for i in range(N):
        seqfile_1 = sequence_list[i]
        for j in range(i+1, N):
            seqfile_2 = sequence_list[j]
            matrix[i][j] = method(seqfile_1, seqfile_2, M, K, Num_Threads, Reverse, P_dir)         
            matrix[j][i] = matrix[i][j]
    return matrix

d2star_matrix_pairwise = partial(dist_matrix_pairwise, method = d2star)
d2shepp_matrix_pairwise = partial(dist_matrix_pairwise, method = d2shepp)
CVTree_matrix_pairwise = partial(dist_matrix_pairwise, method = CVTree)
Ma_matrix_pairwise = partial(dist_matrix_pairwise, method = Ma)
Eu_matrix_pairwise = partial(dist_matrix_pairwise, method = Eu)
d2_matrix_pairwise = partial(dist_matrix_pairwise, method = d2)
 
def error_array(sequence_list, M, K, Num_Threads, P_dir, method):
    N = len(sequence_list)
    array = np.zeros(N)
    for i in range(N):
        seqfile = sequence_list[i]
        array[i] = method(seqfile, M, K, Num_Thread, P_dir)
    return array

d2shepp_error_array = partial(error_array, method = d2shepp_error)
