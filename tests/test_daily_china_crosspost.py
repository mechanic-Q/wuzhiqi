# Language: 中文
import hashlib
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "daily_china_crosspost.py"


class CrosspostWithoutDouyinTests(unittest.TestCase):
    def test_main_flow_has_no_douyin(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn('sau("douyin"', source)
        self.assertNotIn('"douyin"', source)
        self.assertNotIn("Publish 抖音", source)
        self.assertNotIn('"douyin", "tencent"', source)

    def test_retained_platform_blocks_are_byte_stable(self):
        source = SCRIPT.read_text(encoding="utf-8")
        blocks = {
            "bilibili": ("# 5. Publish B站", "# 7. Publish 小红书", "f3b00d33e3ee54492ad45329dc6e76c863fa0851468c60b6c209a41f7c4cf494"),
            "xiaohongshu": ("# 7. Publish 小红书", "# 8. Publish 视频号", "468fbe68178815c526a037c38c4f96608e442387e860bb9ee16a4ce84fa0e936"),
            "tencent": ("# 8. Publish 视频号", "# 9. Summary", "8a361f092f24d7016ecc536043f71ec2442ac4d9e0d0e94c9f6f5c487ec07988"),
        }
        for name, (start, end, expected) in blocks.items():
            with self.subTest(platform=name):
                block = source[source.index(start):source.index(end, source.index(start))]
                self.assertEqual(hashlib.sha256(block.encode()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
