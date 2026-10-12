"""Allowlisted public test evidence. Never serialize logs or exception text."""
import contextlib
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import time
import unittest
from collections import Counter
from datetime import datetime, timezone

from tools.portfolio_cases import PROJECT

STATUSES = {"passed", "failed", "error", "skipped", "expected_failure", "unexpected_success"}
ID = re.compile(r"[A-Za-z0-9_.]+")
SKIPS = {"postgres_not_configured", "symlink_privilege", "optional_dependency", "other_not_published"}


def skip_category(reason):
    reason = str(reason).lower()
    if "postgres" in reason:
        return "postgres_not_configured"
    if "symlink" in reason:
        return "symlink_privilege"
    if "install" in reason or "dependency" in reason:
        return "optional_dependency"
    return "other_not_published"


class PublicResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.records = []
        self.current = {}

    def startTest(self, test):
        super().startTest(test)
        self.started = time.perf_counter()
        identifier = test.id()
        if not ID.fullmatch(identifier):
            raise ValueError("Unsafe test identifier")
        self.current = {"test_id": identifier, "status": "passed"}

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.current["status"] = "failed"

    def addError(self, test, err):
        super().addError(test, err)
        self.current["status"] = "error"

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.current.update(status="skipped", skip_category=skip_category(reason))

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.current["status"] = "expected_failure"

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.current["status"] = "unexpected_success"

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.current["status"] = "failed" if issubclass(err[0], test.failureException) else "error"

    def stopTest(self, test):
        self.current["duration_ms"] = round((time.perf_counter() - self.started) * 1000, 3)
        self.records.append(dict(self.current))
        super().stopTest(test)

    def addDuration(self, test, elapsed):
        pass


def run_suite(suite):
    result = PublicResult()
    # Test stdout, stderr, skip reasons and traceback text stay out of public evidence.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        suite.run(result)
    summary = dict.fromkeys(sorted(STATUSES), 0)
    summary.update(Counter(item["status"] for item in result.records))
    summary["total"] = len(result.records)
    # setUpClass/tearDownClass/module failures may not start an individual test.
    summary["fixture_errors"] = sum(isinstance(test, unittest.suite._ErrorHolder) for test, _ in result.errors)
    return {"summary": summary, "tests": result.records}


def source_identity(root):
    folders = ("src", "tests", "tools", "scripts", "labs", "deploy")
    paths = [p for folder in folders for p in (root / folder).rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}]
    paths += [root / name for name in ("run.py", "pyproject.toml", "requirements-runtime.lock") if (root / name).is_file()]
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        # Git may check text out with CRLF; fingerprint canonical UTF-8 text using LF.
        data = path.read_bytes()
        if path.suffix in {".py", ".js", ".mjs", ".html", ".css", ".md", ".json", ".xml", ".yml", ".yaml", ".toml", ".txt", ".sql", ".sh", ".ps1", ".lock", ".svg"}:
            data = data.replace(b"\r\n", b"\n")
        digest.update(hashlib.sha256(data).digest())
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=15)
    commit = git.stdout.strip()
    return {"base_commit": commit if re.fullmatch(r"[a-f0-9]{40}", commit) else None,
            "tested_files_sha256": digest.hexdigest(), "file_count": len(paths),
            "fingerprint_scope": "src/tests/tools/scripts/labs/deploy plus run.py, pyproject.toml and runtime lock; LF canonicalized"}


def run_checks(root, checks):
    output = []
    node = os.environ.get("NODE", "node")
    for name, args in checks:
        started = time.perf_counter()
        try:
            child = subprocess.run([node, *args], cwd=root, capture_output=True, timeout=300)
            status, code = ("passed" if child.returncode == 0 else "failed"), child.returncode
        except subprocess.TimeoutExpired:
            status, code = "timeout", None
        except OSError:
            status, code = "unavailable", None
        output.append({"check_id": name, "status": status, "exit_code": code,
                       "duration_ms": round((time.perf_counter() - started) * 1000, 3)})
    return output


def validate_public_report(data):
    if set(data) != {"schema_version", "repository", "started_utc", "environment", "source", "data_policy",
                     "limitations", "portfolio", "regression", "additional_checks"}:
        raise ValueError("Unexpected public report field")
    if data["schema_version"] != "1.0":
        raise ValueError("Unsupported report schema")
    if not re.fullmatch(r"[a-z0-9-]+", data["repository"]):
        raise ValueError("Unsafe repository identifier")
    if not re.fullmatch(r"[0-9TZ:.+\-]+", data["started_utc"]):
        raise ValueError("Unsafe timestamp")
    if data["limitations"] != PROJECT["limitations"]:
        raise ValueError("Unreviewed limitations text")
    source = data["source"]
    if set(source) != {"base_commit", "tested_files_sha256", "file_count", "fingerprint_scope"}:
        raise ValueError("Unexpected source metadata")
    if source["base_commit"] is not None and not re.fullmatch(r"[a-f0-9]{40}", source["base_commit"]):
        raise ValueError("Unsafe commit identifier")
    if not re.fullmatch(r"[a-f0-9]{64}", source["tested_files_sha256"]) or type(source["file_count"]) is not int:
        raise ValueError("Unsafe source fingerprint")
    if source["fingerprint_scope"] != "src/tests/tools/scripts/labs/deploy plus run.py, pyproject.toml and runtime lock; LF canonicalized":
        raise ValueError("Unsafe fingerprint scope")
    if data["data_policy"] != "Only test IDs, outcomes, counts, timings and code-owned descriptions are exported. No raw logs, exception text, paths, account names, IPs, tokens or browser screenshots.":
        raise ValueError("Unsafe data policy text")
    env = data["environment"]
    if set(env) != {"os", "python"} or env["os"] not in {"Windows", "Linux", "Darwin", "other"} or not re.fullmatch(r"[0-9.]+", env["python"]):
        raise ValueError("Unsafe environment metadata")
    for suite_name in ("portfolio", "regression"):
        suite = data[suite_name]
        if suite is None:
            continue
        if set(suite) != {"summary", "tests"} or set(suite["summary"]) != STATUSES | {"total", "fixture_errors"}:
            raise ValueError("Unexpected suite field")
        if any(type(value) is not int or value < 0 for value in suite["summary"].values()):
            raise ValueError("Invalid suite counts")
        counted = Counter()
        for item in suite["tests"]:
            if set(item) - {"test_id", "status", "duration_ms", "skip_category", "case_id", "title"}:
                raise ValueError("Unexpected test evidence field")
            if not ID.fullmatch(item["test_id"]) or item["status"] not in STATUSES:
                raise ValueError("Unsafe test evidence")
            if type(item["duration_ms"]) not in {int, float} or not 0 <= item["duration_ms"] < 1e12:
                raise ValueError("Invalid duration")
            if "skip_category" in item and item["skip_category"] not in SKIPS:
                raise ValueError("Unsafe skip category")
            if suite_name == "portfolio":
                expected = {identifier: (f"P{index:02}", title) for index, (title, identifier) in enumerate(PROJECT["cases"], 1)}
                case = expected.get(item["test_id"], ("LOAD_ERROR", "Test could not be loaded"))
                if (item.get("case_id"), item.get("title")) != case:
                    raise ValueError("Unreviewed scenario description")
            elif set(item) - {"test_id", "status", "duration_ms", "skip_category"}:
                raise ValueError("Unexpected regression metadata")
            counted[item["status"]] += 1
        if suite["summary"]["total"] != len(suite["tests"]) or any(suite["summary"][key] != counted[key] for key in STATUSES):
            raise ValueError("Inconsistent public counts")
    allowed_checks = {name for name, _ in PROJECT["checks"]}
    for item in data["additional_checks"]:
        if set(item) != {"check_id", "status", "exit_code", "duration_ms"} or item["check_id"] not in allowed_checks:
            raise ValueError("Unreviewed subprocess evidence")
        if item["status"] not in {"passed", "failed", "timeout", "unavailable"}:
            raise ValueError("Unsafe subprocess status")
        if item["exit_code"] is not None and type(item["exit_code"]) is not int:
            raise ValueError("Unsafe subprocess exit code")
        if type(item["duration_ms"]) not in {int, float} or not 0 <= item["duration_ms"] < 1e12:
            raise ValueError("Invalid subprocess duration")
    # No text from input events or exceptions is accepted. Remaining strings are code-owned constants.
    return data


def make_report(root, project, portfolio, regression, checks, started):
    data = {"schema_version": "1.0", "repository": root.name, "started_utc": started,
            "environment": {"os": platform.system() if platform.system() in {"Windows", "Linux", "Darwin"} else "other",
                            "python": platform.python_version()},
            "source": source_identity(root),
            "data_policy": "Only test IDs, outcomes, counts, timings and code-owned descriptions are exported. No raw logs, exception text, paths, account names, IPs, tokens or browser screenshots.",
            "limitations": project["limitations"], "portfolio": portfolio, "regression": regression,
            "additional_checks": checks}
    return validate_public_report(data)


def markdown_report(data):
    lines = ["# 로컬 공개 테스트 기록", "", f"- 저장소: `{data['repository']}`",
             f"- 실행 시각(UTC): `{data['started_utc']}`",
             f"- 환경: {data['environment']['os']} / Python {data['environment']['python']}",
             f"- 검사 당시 기준 커밋: `{data['source']['base_commit']}`",
             "- 보고서는 아직 커밋되지 않은 테스트 실행기 변경을 포함한 작업 트리를 검사한 결과입니다.",
             f"- 검사 대상 파일 {data['source']['file_count']}개의 정규화 SHA-256: `{data['source']['tested_files_sha256']}`",
             "- 위 값은 소스 지문이며 개인 파일 해시나 디지털 서명이 아닙니다.", "",
             "## 대표 시나리오 10개", "",
             "기존 테스트 중 서로 다른 기능 10개를 선정하여 별도 재실행했습니다. 전체 회귀 검사와 중복되므로 독립 표본 20개로 합산하지 않습니다.", ""]
    for item in data["portfolio"]["tests"]:
        lines += [f"- **{item['case_id']}: {item['title']}**",
                  f"  결과: `{item['status']}`, {item['duration_ms']} ms. 재현 대상: `{item['test_id']}`."]
    if data["regression"]:
        summary = data["regression"]["summary"]
        lines += ["", "## 전체 자동 테스트", "",
                  f"실행 {summary['total']}개: 통과 {summary['passed']}, 실패 {summary['failed']}, 오류 {summary['error']}, 건너뜀 {summary['skipped']}, fixture 오류 {summary['fixture_errors']}.",
                  "전체 테스트별 결과와 소요 시간은 같은 폴더의 JSON에 기록했습니다."]
        skipped = Counter(item.get("skip_category") for item in data["regression"]["tests"] if item["status"] == "skipped")
        lines += [f"- 건너뜀 사유 코드 `{key}`: {value}개." for key, value in sorted(skipped.items())]
    lines += ["", "## 웹 검증", ""]
    lines += [f"- `{item['check_id']}`: **{item['status']}**, 종료 코드 {item['exit_code']}, {item['duration_ms']} ms."
              for item in data["additional_checks"]] or ["이번 실행에는 웹 검증을 포함하지 않았습니다."]
    lines += ["", "## 공개 정보 범위", "",
              "개인 폴더를 임의로 탐색하지 않았습니다. 테스트 코드가 지정한 프로젝트 파일과 격리된 임시 테스트 자료만 사용했습니다.",
              "로그·계정·호스트·IP·명령줄·DB·세션/소스 토큰·예외 상세·절대 경로·브라우저 화면은 공개 보고서에서 제외했습니다.",
              "기존 샘플의 이름은 가상 식별자이며 실제 개인정보를 단순 가명 처리한 자료가 아닙니다.",
              "임시 DB 비밀번호·암호화 키·인증 토큰은 테스트 실행 중 생성되거나 코드의 명시적 테스트용 값이며 보고서로 내보내지 않습니다.",
              "", "## 한계", ""]
    lines += [f"- {value}" for value in data["limitations"]]
    lines += ["- 성공은 해당 테스트의 기대 동작 일치이며 안전 인증·무결점·법적 적합성 보증이 아닙니다.",
              "- 소요 시간은 이 PC의 단일 실행 관측값이며 성능 벤치마크가 아닙니다.",
              "- 이 문서의 로컬 결과와 GitHub Actions의 원격 결과는 별개입니다.", "",
              "## 재현", "", "```console",
              "python tools/run_portfolio_validation.py --suite all --browser --output reports/local-validation.json",
              "```", "",
              "Python 및 선택 의존성과 Playwright/Chromium 설치 방법은 README를 참고하세요.",
              "대표 10개만 실행: `python tools/run_portfolio_validation.py --suite portfolio`.",
              "개별 시나리오는 위 테스트 ID를 `python -m unittest <test_id> -v`로 실행할 수 있습니다.",
              "PostgreSQL은 기본적으로 실행하지 않습니다. 운영 DB가 아닌 별도 테스트 DB에만 명시적으로 허용하세요.", ""]
    return "\n".join(lines)

