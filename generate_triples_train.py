import os
import argparse
import json
import random
from pyserini.search import SimpleSearcher
from tqdm import tqdm


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=str, required=True)
    parser.add_argument('--output', type=str, required=True)
    parser.add_argument('--output_ids', type=str, required=True)
    parser.add_argument('--corpus', type=str, required=True)
    parser.add_argument('--index', type=str, default='msmarco-passage')
    parser.add_argument('--max_hits', type=int, default=1000)

    args = parser.parse_args()

    if os.path.isdir(args.index):
        searcher = SimpleSearcher(args.index)
    else:
        searcher = SimpleSearcher.from_prebuilt_index(args.index)

    corpus = {}
    with open(args.corpus, 'r', encoding='utf8') as f:
        for line in tqdm(f, desc='Loading Corpus'):
            doc_id, doc_text = line.strip().split('\t')
            corpus[doc_id] = doc_text

    mrr = 0.0
    recall = 0.0
    n_no_query = 0
    n_docs_not_found = 0
    n_good_equal_bad = 0
    n_examples = 0
    with open(args.input) as f, open(args.output, 'w') as fout, open(args.output_ids, 'w') as fout_ids:
        for line_num, line in tqdm(enumerate(f)):
            row = json.loads(line.strip())

            if not row['question']:
                n_no_query += 1
                continue

            question = ' '.join(row['question'].split())  # Removes line breaks and tabs.

            if args.skip_good_equal_bad:
                if 'bad_question' in row:
                    bad_question = ' '.join(row['bad_question'].split())
                    if question.lower() == bad_question.lower():
                        n_good_equal_bad += 1
                        continue

            retrieve = True
            if args.bad_questions_as_negatives:
                if 'bad_question' in row:
                    bad_question = ' '.join(row['bad_question'].split())
                    if question.lower() != bad_question.lower():
                        retrieve = False
                        fout.write(f'{question}\t{row["doc_text"]}\t\n')
                        fout.write(f'{bad_question}\t\t{row["doc_text"]}\n')
                        fout_ids.write(f'{line_num}\t{row["doc_id"]}\t{row["doc_id"]}\n')
                        fout_ids.write(f'{line_num}\t{row["doc_id"]}\t{row["doc_id"]}\n')
                    else:
                        n_good_equal_bad += 1

            if retrieve:
                hits = searcher.search(question, k=args.max_hits + 1)
                n_examples += 1
                sampled_ranks = random.sample(range(len(hits)), min(len(hits), args.n_samples + 1))
                n_samples_so_far = 0
                for rank, hit in enumerate(hits):
                    neg_doc_id= hit.docid
                    if neg_doc_id == row['doc_id']:
                        mrr += 1 / (rank + 1)
                        recall += 1
                        continue

                    if rank not in sampled_ranks:
                        continue

                    if neg_doc_id not in corpus:
                        n_docs_not_found += 1
                        continue

                    neg_doc_text = corpus[neg_doc_id]

                    fout.write(f'{question}\t{row["doc_text"]}\t{neg_doc_text}\n')
                    fout_ids.write(f'{line_num}\t{row["doc_id"]}\t{neg_doc_id}\n')
                    n_samples_so_far += 1
                    if n_samples_so_far >= args.n_samples:
                        break

    if not args.bad_questions_as_negatives: 
        print(f'MRR BM25: {mrr / n_examples}')
        print(f'Recall@{args.max_hits} BM25: {recall / n_examples}')
    print(f'{n_no_query} lines without queries.')
    print(f'{n_docs_not_found} docs returned by the search engine but not found in the corpus.')
    print(f'{n_good_equal_bad} good queries equal to bad ones.')

    print('Done!')
