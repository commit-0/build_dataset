import sys
from datasets import load_dataset


def clean_columns(dataset):
    keys_to_remove = [key for key in dataset.column_names if key not in ["canonical_solution", "test", "instance_id", "prompt"]]
    return dataset.remove_columns(keys_to_remove)

def convert_mbpp_tests(assert_list):
    # Generate individual test functions
    test_functions = []
    for i, assert_line in enumerate(assert_list, 1):
        test_func = f"def test{i}():\n    {assert_line}"
        test_functions.append(test_func)

    return "\n\n".join(test_functions)

def convert_humaneval_tests(test_code, entrypoint):
    # Split the input into lines and clean up
    lines = test_code.strip().split("\n")

    # Find all assert lines
    assert_lines = [line for line in lines if line.lstrip().startswith("assert")]

    # Generate individual test functions
    test_functions = [f"candidate = {entrypoint}"]
    for i, assert_line in enumerate(assert_lines, 1):
        test_func = f"def test{i}():\n{assert_line}"
        test_functions.append(test_func)

    return "\n\n".join(test_functions)

def convert_humaneval():
    ds = load_dataset("openai/openai_humaneval")
    for split in ds:
        ds[split] = ds[split].rename_column('task_id', 'instance_id')
        tests = [convert_humaneval_tests(one['test'], one['entry_point']) for one in ds[split]]
        ds[split] = ds[split].remove_columns(['test'])
        ds[split] = ds[split].add_column(name='test', column=tests)
        ds[split] = clean_columns(ds[split])
    out_name = f"commit0/openai_humaneval"
    ds.push_to_hub(out_name)

def convert_codecontests():
    pass

def convert_bigcodebench():
    pass

def convert_mbpp():
    ds = load_dataset("google-research-datasets/mbpp")
    for split in ds:
        ds[split] = ds[split].rename_column('task_id', 'instance_id')
        ds[split] = ds[split].rename_column('code', 'canonical_solution')
        ds[split] = ds[split].add_column(name='test', column=[convert_mbpp_tests(one) for one in ds[split]['test_list']])
        ds[split] = clean_columns(ds[split])
    out_name = f"commit0/mbpp"
    ds.push_to_hub(out_name)

if __name__ == "__main__":
    data = sys.argv[1].lower()
    if data == "mbpp":
        convert_mbpp()
    elif data == "humaneval":
        convert_humaneval()
    elif data == "codecontests":
        convert_codecontests()
    elif data == "bigcodebench":
        convert_bigcodebench()
    else:
        raise NotImplementedError()

