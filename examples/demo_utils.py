"""Demo module for complexity regression audit (O(n) baseline on main)."""


def find_duplicates(lst):
    seen = set()
    result = []
    for x in lst:
        if x in seen:
            result.append(x)
        seen.add(x)
    return result
