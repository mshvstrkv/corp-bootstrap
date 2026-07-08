from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from migrators import root_pom


class XmlFormattingTest(unittest.TestCase):
    def test_written_xml_is_readable_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "service-app").mkdir()
            (Path(tmp) / "service-app" / "pom.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion><artifactId>x-app</artifactId></project>
""",
                encoding="utf-8",
            )
            (Path(tmp) / "service-app" / "src").mkdir()
            pom = Path(tmp) / "pom.xml"
            pom.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion><groupId>com.example</groupId><artifactId>x</artifactId><version>1.0.0</version><description>X</description></project>
""",
                encoding="utf-8",
            )

            root_pom.migrate(pom)
            first = pom.read_text(encoding="utf-8")
            second = root_pom.migrate(pom)

            self.assertIn("\n    <modules>", first)
            self.assertFalse(second.changed)


if __name__ == "__main__":
    unittest.main()
