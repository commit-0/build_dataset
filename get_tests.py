import bz2
from datasets import load_dataset
from tqdm import tqdm

ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
for one in tqdm(ds):
    instance_id = one["instance_id"]
    with bz2.open(f"tests/{instance_id}#pass_to_pass.bz2", "wt") as bz_file:
        bz_file.write('\n'.join(eval(one["PASS_TO_PASS"])))
    with bz2.open(f"tests/{instance_id}#fail_to_pass.bz2", "wt") as bz_file:
        bz_file.write('\n'.join(eval(one["FAIL_TO_PASS"])))
        print('\n'.join(one["FAIL_TO_PASS"]))
