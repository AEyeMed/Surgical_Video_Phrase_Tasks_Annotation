import unittest

from surgui.theme import (
    THEME_DOCUMENTS,
    accessibility_pairs,
    build_stylesheet,
    contrast_ratio,
    load_theme,
    non_text_accessibility_pairs,
)


class ThemeTokenTests(unittest.TestCase):
    def test_every_theme_document_provides_complete_qss(self):
        for theme_id in THEME_DOCUMENTS:
            tokens = load_theme(theme_id)
            self.assertGreater(len(build_stylesheet(theme_id)), 4_000)
            self.assertEqual(tokens.identifier, theme_id)

    def test_required_text_pairs_meet_wcag_aa(self):
        for theme_id in THEME_DOCUMENTS:
            tokens = load_theme(theme_id)
            for role, foreground, background in accessibility_pairs(tokens):
                with self.subTest(theme=theme_id, role=role):
                    self.assertGreaterEqual(contrast_ratio(foreground, background), 4.5)

    def test_critical_non_text_pairs_meet_wcag_aa_component_contrast(self):
        for theme_id in THEME_DOCUMENTS:
            tokens = load_theme(theme_id)
            for role, foreground, background in non_text_accessibility_pairs(tokens):
                with self.subTest(theme=theme_id, role=role):
                    self.assertGreaterEqual(contrast_ratio(foreground, background), 3.0)


if __name__ == "__main__":
    unittest.main()
