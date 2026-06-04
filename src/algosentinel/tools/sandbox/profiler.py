"""
R5 composability chain (step 1):
  sandbox.profile_runtime → list[TimingPoint]
  → consumed by complexity.fit_complexity_curves
"""

import json
import re

from pydantic import BaseModel, Field

from algosentinel.models.sandbox import (
    BenchmarkPairResult,
    BenchmarkPoint,
    CorrectnessResult,
    MemoryPoint,
    TimingPoint,
)
from algosentinel.tools.registry import tool
from algosentinel.tools.sandbox.executor import _exec_in_container, _get_container

TIMING_TEMPLATE = """
import time, statistics, json, random

{function_code}

def _generate_input(input_type, n, seed=42):
    random.seed(seed)
    if input_type == "list_int":
        return [random.randint(0, n*10) for _ in range(n)]
    elif input_type == "list_str":
        return ["".join(random.choices("abcdefghij", k=5)) for _ in range(n)]
    elif input_type == "dict":
        return {{str(i): random.randint(0, 100) for i in range(n)}}
    else:
        return [random.randint(0, n*10) for _ in range(n)]

inputs = _generate_input("{input_type}", {n}, seed=42)
times = []
for _ in range({runs}):
    start = time.perf_counter()
    {function_name}(inputs)
    times.append((time.perf_counter() - start) * 1000)

print(json.dumps({{
    "input_size": {n},
    "mean_ms": statistics.mean(times),
    "std_ms": statistics.stdev(times) if len(times) > 1 else 0.0,
    "runs": {runs}
}}))
"""


class ProfileRuntimeInput(BaseModel):
    sandbox_id: str
    code: str
    function_name: str
    input_sizes: list[int] = Field(default=[10, 50, 100, 500, 1000, 5000, 10000])
    runs_per_size: int = 5
    input_type: str = "list_int"


class ProfileMemoryInput(BaseModel):
    sandbox_id: str
    code: str
    function_name: str
    input_sizes: list[int]


class BenchmarkFunctionPairInput(BaseModel):
    sandbox_id: str
    pre_code: str
    post_code: str
    function_name: str
    input_sizes: list[int] = Field(default=[10, 100, 1000, 10000])


class ValidateCorrectnessInput(BaseModel):
    sandbox_id: str
    pre_code: str
    post_code: str
    function_name: str
    test_input_sizes: list[int] = Field(default=[10, 100, 1000])


def _parse_timing_json(stdout: str) -> dict | None:
    for line in stdout.strip().splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    match = re.search(r"\{[^{}]*\"input_size\"[^{}]*\}", stdout)
    if match:
        return json.loads(match.group())
    return None


@tool(
    namespace="sandbox",
    description="Benchmark a function at multiple input sizes; returns TimingPoints for curve fitting.",
    input_model=ProfileRuntimeInput,
    output_model=list,
)
def profile_runtime(inp: ProfileRuntimeInput) -> list[TimingPoint]:
    container = _get_container(inp.sandbox_id)
    points: list[TimingPoint] = []
    for n in inp.input_sizes:
        script = TIMING_TEMPLATE.format(
            function_code=inp.code,
            input_type=inp.input_type,
            n=n,
            runs=inp.runs_per_size,
            function_name=inp.function_name,
        )
        stdout, stderr, exit_code = _exec_in_container(container, script)
        if exit_code != 0:
            continue
        data = _parse_timing_json(stdout)
        if data:
            points.append(
                TimingPoint(
                    input_size=data["input_size"],
                    elapsed_ms=data["mean_ms"],
                    std_dev_ms=data.get("std_ms", 0.0),
                    runs=data.get("runs", inp.runs_per_size),
                )
            )
    return points


@tool(
    namespace="sandbox",
    description="Profile peak memory usage with tracemalloc at multiple input sizes.",
    input_model=ProfileMemoryInput,
    output_model=list,
)
def profile_memory(inp: ProfileMemoryInput) -> list[MemoryPoint]:
    container = _get_container(inp.sandbox_id)
    points: list[MemoryPoint] = []
    for n in inp.input_sizes:
        code = f"""
import tracemalloc, json, random
{inp.code}
random.seed(42)
data = [random.randint(0, n*10) for _ in range({n})]
tracemalloc.start()
{inp.function_name}(data)
_, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
print(json.dumps({{"input_size": {n}, "peak_bytes": peak}}))
"""
        stdout, _, exit_code = _exec_in_container(container, code)
        if exit_code == 0:
            data = _parse_timing_json(stdout)
            if data:
                points.append(
                    MemoryPoint(input_size=data["input_size"], peak_bytes=data["peak_bytes"])
                )
    return points


@tool(
    namespace="sandbox",
    description="Time pre and post function versions side by side.",
    input_model=BenchmarkFunctionPairInput,
    output_model=BenchmarkPairResult,
)
def benchmark_function_pair(inp: BenchmarkFunctionPairInput) -> BenchmarkPairResult:
    pre_points = profile_runtime(
        ProfileRuntimeInput(
            sandbox_id=inp.sandbox_id,
            code=inp.pre_code,
            function_name=inp.function_name,
            input_sizes=inp.input_sizes,
        )
    )
    post_points = profile_runtime(
        ProfileRuntimeInput(
            sandbox_id=inp.sandbox_id,
            code=inp.post_code,
            function_name=inp.function_name,
            input_sizes=inp.input_sizes,
        )
    )
    post_by_size = {p.input_size: p.elapsed_ms for p in post_points}
    bench_points: list[BenchmarkPoint] = []
    for pre in pre_points:
        post_ms = post_by_size.get(pre.input_size, pre.elapsed_ms)
        ratio = post_ms / pre.elapsed_ms if pre.elapsed_ms > 0 else 1.0
        bench_points.append(
            BenchmarkPoint(
                input_size=pre.input_size,
                pre_elapsed_ms=pre.elapsed_ms,
                post_elapsed_ms=post_ms,
                ratio=ratio,
            )
        )
    return BenchmarkPairResult(function_name=inp.function_name, points=bench_points)


@tool(
    namespace="sandbox",
    description="Compare pre and post function outputs for correctness.",
    input_model=ValidateCorrectnessInput,
    output_model=CorrectnessResult,
)
def validate_correctness(inp: ValidateCorrectnessInput) -> CorrectnessResult:
    container = _get_container(inp.sandbox_id)
    failed: list = []
    for n in inp.test_input_sizes:
        code = f"""
import json, random
{inp.pre_code}
{inp.post_code}
random.seed(42)
data = [random.randint(0, {n}*10) for _ in range({n})]
pre_out = {inp.function_name}(data)
# redefine post with suffix
exec({inp.post_code!r})
post_fn = {inp.function_name}
post_out = post_fn(data)
print(json.dumps({{"match": pre_out == post_out}}))
"""
        combined = f"""
import json, random
{inp.pre_code}

def _pre(data):
    return {inp.function_name}(data)

{inp.post_code.replace(f"def {inp.function_name}", f"def _post")}

random.seed(42)
data = list(range({n}))
try:
    match = _pre(data) == _post(data)
except Exception as e:
    print(json.dumps({{"match": False, "error": str(e)}}))
else:
    print(json.dumps({{"match": match}}))
"""
        stdout, _, exit_code = _exec_in_container(container, combined)
        if exit_code != 0:
            failed.append(n)
            continue
        data = _parse_timing_json(stdout)
        if not data or not data.get("match"):
            failed.append(n)
    return CorrectnessResult(
        is_correct=len(failed) == 0,
        failed_inputs=failed,
        error_message=None if not failed else f"Mismatch at sizes: {failed}",
    )
