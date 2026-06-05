"""Demo module — intentional O(n^2) regression for agent audit."""

def find_duplicates(lst):
    result = []
    for i, x in enumerate(lst):
        if x in lst[:i]:
            result.append(x)
    return result
