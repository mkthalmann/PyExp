dict_a = {"a": 1, "b": 2}
dict_b = {k: dict_a[k] for k in ('a')}

print(str(dict_b))
