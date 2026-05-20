import unittest

from desktop_py.core.parser import convert_timestamp, extract_labeled_datetime


class ParserTestCase(unittest.TestCase):
    def test_full_format(self):
        """完整日期时间格式"""
        text = "处理截止时间：2026-04-20 19:07:26 申诉截止时间：2026-04-21 10:19:34"
        self.assertEqual(extract_labeled_datetime(text, "处理截止时间"), "2026-04-20 19:07:26")

    def test_date_only(self):
        """仅日期，无具体时间"""
        text = "处理截止时间：2026-04-20 剩余1天"
        self.assertEqual(extract_labeled_datetime(text, "处理截止时间"), "2026-04-20")

    def test_chinese_year(self):
        """中文年格式"""
        text = "处理截止时间：2026年04月20日 19:07:26"
        self.assertEqual(extract_labeled_datetime(text, "处理截止时间"), "2026年04月20日 19:07:26")

    def test_chinese_year_no_time(self):
        """中文年格式无时间"""
        text = "处理截止时间：2026年04月20日"
        self.assertEqual(extract_labeled_datetime(text, "处理截止时间"), "2026年04月20日")

    def test_slash_separator(self):
        """斜杠分隔"""
        text = "处理截止时间：2026/04/20 19:07:26"
        self.assertEqual(extract_labeled_datetime(text, "处理截止时间"), "2026/04/20 19:07:26")

    def test_dot_separator(self):
        """点分隔年月日"""
        text = "处理截止时间：2026.04.20 19:07:26"
        self.assertEqual(extract_labeled_datetime(text, "处理截止时间"), "2026.04.20 19:07:26")

    def test_T_separator(self):
        """T 分隔日期时间"""
        text = "处理截止时间：2026-04-20T19:07:26Z"
        self.assertEqual(extract_labeled_datetime(text, "处理截止时间"), "2026-04-20T19:07:26")

    def test_no_colon_after_label(self):
        """标签后无冒号，直接空格"""
        text = "处理截止时间 2026-04-20 19:07:26"
        self.assertEqual(extract_labeled_datetime(text, "处理截止时间"), "2026-04-20 19:07:26")

    def test_missing_label(self):
        """文本中不存在目标标签"""
        text = "申诉截止时间：2026-04-21 10:19:34"
        self.assertEqual(extract_labeled_datetime(text, "处理截止时间"), "")

    def test_empty_text(self):
        """空文本"""
        self.assertEqual(extract_labeled_datetime("", "处理截止时间"), "")

    def test_no_date_after_label(self):
        """标签后没有有效日期"""
        text = "处理截止时间：无"
        self.assertEqual(extract_labeled_datetime(text, "处理截止时间"), "")

    def test_multiline(self):
        """多行文本"""
        text = "订单号：12345\n处理截止时间：2026-04-20 19:07:26\n申诉截止时间：2026-04-21 10:19:34"
        self.assertEqual(extract_labeled_datetime(text, "处理截止时间"), "2026-04-20 19:07:26")

    def test_extra_spaces(self):
        """标签和日期之间有多余空格"""
        text = "处理截止时间：    2026-04-20 19:07:26"
        self.assertEqual(extract_labeled_datetime(text, "处理截止时间"), "2026-04-20 19:07:26")

    def test_申诉_label(self):
        """申诉截止时间标签"""
        text = "申诉截止时间：2026-04-21 10:19:34"
        self.assertEqual(extract_labeled_datetime(text, "申诉截止时间"), "2026-04-21 10:19:34")

    def test_special_chars_in_label(self):
        """标签含特殊字符"""
        text = "处理截止时间(重要)：2026-04-20 19:07:26"
        self.assertEqual(extract_labeled_datetime(text, "处理截止时间(重要)"), "2026-04-20 19:07:26")

    def test_convert_timestamp(self):
        """10 位时间戳转日期"""
        self.assertEqual(convert_timestamp("1776737974"), "2026-04-21 10:19:34")

    def test_convert_timestamp_already_date(self):
        """已经是日期字符串"""
        self.assertEqual(convert_timestamp("2026-04-21 10:19:34"), "2026-04-21 10:19:34")

    def test_convert_timestamp_empty(self):
        """空字符串"""
        self.assertEqual(convert_timestamp(""), "")

    def test_convert_timestamp_non_digit(self):
        """非数字非日期"""
        self.assertEqual(convert_timestamp("未知"), "未知")

    def test_convert_timestamp_short_digits(self):
        """不足 10 位数字"""
        self.assertEqual(convert_timestamp("123456"), "123456")
