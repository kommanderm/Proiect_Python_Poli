"""Run the suite with readable output: `python -m tests` (run.py does this before starting the server)."""

import os
import sys
import time
import unittest
from collections import Counter
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

# worst first wins when one test reports several outcomes (one per failing subtest)
SEVERITY = ["pass", "skip", "fail", "error"]
ICONS = {"pass": ("✓", "32"), "skip": ("-", "33"), "fail": ("✗", "31"), "error": ("!", "31")}


def use_color(stream):
    if os.environ.get("NO_COLOR"):
        return False
    return bool(os.environ.get("FORCE_COLOR")) or stream.isatty()


class PrettyResult(unittest.TestResult):
    def __init__(self, stream):
        super().__init__()
        self.stream = stream  # unittest also uses this to decide whether to colour tracebacks
        self.color = use_color(stream)
        self.group = None
        self.status = "pass"
        self.counts = Counter()

    def paint(self, text, code):
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def write(self, text=""):
        self.stream.write(text + "\n")
        self.stream.flush()

    def mark(self, status):
        self.status = max(self.status, status, key=SEVERITY.index)

    def startTest(self, test):
        super().startTest(test)
        group = f"{type(test).__module__.removeprefix('tests.test_')} › {type(test).__name__}"
        if group != self.group:
            self.group = group
            self.write(f"\n  {self.paint(group, '1')}")
        self.status = "pass"
        self.started = time.perf_counter()

    def stopTest(self, test):
        super().stopTest(test)
        icon, color = ICONS[self.status]
        name = getattr(test, "_testMethodName", str(test)).removeprefix("test_").replace("_", " ")
        ms = (time.perf_counter() - self.started) * 1000
        self.write(f"    {self.paint(icon, color)} {name} {self.paint(f'{ms:.0f}ms', '2')}")
        self.counts[self.status] += 1

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.mark("fail")

    def addError(self, test, err):
        super().addError(test, err)
        self.mark("error")

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.mark("fail" if issubclass(err[0], test.failureException) else "error")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.mark("skip")

    def summary(self, seconds):
        for label, entries in (("FAIL", self.failures), ("ERROR", self.errors)):
            for test, trace in entries:
                self.write(f"\n{self.paint(f' {label} ', '1;41')} {self.paint(str(test), '1')}")
                self.write(trace.rstrip())

        parts = [self.paint(f"{self.counts['pass']} passed", "32")]
        for status, word, color in (("fail", "failed", "31"), ("error", "errored", "31"), ("skip", "skipped", "33")):
            if self.counts[status]:
                parts.append(self.paint(f"{self.counts[status]} {word}", color))

        if self.wasSuccessful():
            verdict = self.paint("✓ all tests passed", "1;32")
        else:
            verdict = self.paint("✗ tests failed", "1;31")
        self.write(f"\n  {self.paint('─' * 48, '2')}")
        self.write(f"  {verdict}   {', '.join(parts)} {self.paint(f'in {seconds:.2f}s', '2')}\n")


def main():
    # failure messages can contain lone surrogates (see the sanitising tests); print them escaped
    sys.stdout.reconfigure(errors="backslashreplace")
    suite = unittest.defaultTestLoader.discover(str(TESTS_DIR), top_level_dir=str(TESTS_DIR.parent))
    result = PrettyResult(sys.stdout)
    result.write(result.paint("minichat tests", "1"))

    started = time.perf_counter()
    result.startTestRun()
    suite.run(result)
    result.stopTestRun()
    result.summary(time.perf_counter() - started)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
