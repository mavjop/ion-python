# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
This module
"""
import gc
import tempfile
import platform
import time
import timeit

from amazon.ionbenchmark.benchmark_spec import BenchmarkSpec
import amazon.ionbenchmark.Format as _format

_pypy = platform.python_implementation() == 'PyPy'
if not _pypy:
    import tracemalloc


class BenchmarkResult:
    """
    Results generated by the `run_benchmark` function.

     * `timings` is a list of numbers representing the number of nanoseconds to complete each iteration
     * `batch_size` is the number of times the function was invoked in each iteration
     * `peak_memory_usage` is the peak memory allocated during a single run of the benchmark function, in bytes
    """
    timings = None
    batch_size = None
    peak_memory_usage = None

    def __init__(self, timings, batch_size, peak_memory_usage):
        self.timings = timings
        self.batch_size = batch_size
        self.peak_memory_usage = peak_memory_usage


def run_benchmark(benchmark_spec: BenchmarkSpec):
    """
    Run benchmarks for `benchmark_spec`.
    """
    test_fun = _create_test_fun(benchmark_spec)

    # memory profiling
    if _pypy:
        peak_memory_usage = None
    else:
        peak_memory_usage = _trace_memory_allocation(test_fun)

    setup = ""
    if benchmark_spec["py_gc_disabled"]:
        setup += "import gc; gc.disable()"
    else:
        setup += "import gc; gc.enable()"

    timer = timeit.Timer(stmt=test_fun, timer=time.perf_counter_ns, setup=setup)

    # warm up
    timer.timeit(benchmark_spec.get_warmups())

    # iteration
    (batch_size, _) = timer.autorange()
    timings = timer.repeat(benchmark_spec.get_iterations(), batch_size)

    return BenchmarkResult(timings, batch_size, peak_memory_usage)


def _create_test_fun(benchmark_spec: BenchmarkSpec):
    """
    Create a benchmark function for the given `benchmark_spec`.
    """
    loader_dumper = benchmark_spec.get_loader_dumper()
    match_arg = [benchmark_spec.get_io_type(), benchmark_spec.get_command(), benchmark_spec.get_api()]

    if match_arg == ['buffer', 'read', 'load_dump']:
        with open(benchmark_spec.get_input_file(), 'rb') as f:
            buffer = f.read()

        def test_fn():
            return loader_dumper.loads(buffer)

    elif match_arg == ['buffer', 'write', 'load_dump']:
        data_obj = benchmark_spec.get_data_object()

        def test_fn():
            return loader_dumper.dumps(data_obj)

    elif match_arg == ['file', 'read', 'load_dump']:
        data_file = benchmark_spec.get_input_file()

        def test_fn():
            with open(data_file, "rb") as f:
                return loader_dumper.load(f)

    elif match_arg == ['file', 'write', 'load_dump']:
        data_obj = benchmark_spec.get_data_object()
        data_format = benchmark_spec.get_format()
        if _format.format_is_binary(data_format) or _format.format_is_ion(data_format):
            def test_fn():
                with tempfile.TemporaryFile(mode="wb") as f:
                    return loader_dumper.dump(data_obj, f)
        else:
            def test_fn():
                with tempfile.TemporaryFile(mode="wt") as f:
                    return loader_dumper.dump(data_obj, f)

    else:
        raise NotImplementedError(f"Argument combination not supported: {match_arg}")

    return test_fn


def _trace_memory_allocation(test_fn, *args, **kwargs):
    """
    Measure the memory allocations in bytes for a single invocation of test_fn
    """
    gc.disable()
    tracemalloc.start()
    test_fn(*args, **kwargs)
    memory_usage_peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    gc.enable()
    return memory_usage_peak
