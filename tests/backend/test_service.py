import unittest

from app.modules.detection.service import DetectionService
from app.modules.detection.schemas import ProbeFinding


class DetectionServiceTest(unittest.TestCase):
    def test_should_ignore_skipped_findings_when_calculating_trust_score(self) -> None:
        findings = [
            ProbeFinding(
                probe_name="parameter_probe",
                status="pass",
                score=90,
                summary="ok",
            ),
            ProbeFinding(
                probe_name="tokenizer_probe",
                status="skip",
                score=0,
                summary="skip",
            ),
            ProbeFinding(
                probe_name="response_probe",
                status="warn",
                score=70,
                summary="warn",
            ),
        ]

        score = DetectionService._calculate_trust_score(findings)

        self.assertEqual(score, 80)
