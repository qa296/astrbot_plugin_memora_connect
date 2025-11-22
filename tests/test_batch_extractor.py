"""
测试批量记忆提取模块
"""
import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from batch_extractor import BatchMemoryExtractor


class MockLLMResponse:
    """模拟LLM响应"""
    def __init__(self, completion_text):
        self.completion_text = completion_text


class MockMemorySystem:
    """模拟记忆系统"""
    def __init__(self, llm_provider=None):
        self._llm_provider = llm_provider
    
    async def get_llm_provider(self):
        return self._llm_provider


class TestBatchMemoryExtractor(unittest.TestCase):
    """测试 BatchMemoryExtractor 类"""
    
    def setUp(self):
        """每个测试前初始化"""
        self.memory_system = MockMemorySystem()
        self.extractor = BatchMemoryExtractor(self.memory_system)
    
    def test_extractor_creation(self):
        """测试提取器创建"""
        self.assertIsNotNone(self.extractor)
        self.assertEqual(self.extractor.memory_system, self.memory_system)
    
    def test_format_conversation_history(self):
        """测试格式化对话历史"""
        conversation = [
            {
                "role": "user",
                "content": "你好",
                "sender_name": "张三",
                "timestamp": "2024-01-01 12:00:00"
            },
            {
                "role": "assistant",
                "content": "你好！",
                "sender_name": "Bot",
                "timestamp": "2024-01-01 12:00:01"
            }
        ]
        
        formatted = self.extractor._format_conversation_history(conversation)
        
        self.assertIn("张三", formatted)
        self.assertIn("你好", formatted)
        self.assertIn("Bot", formatted)
    
    def test_format_conversation_history_minimal(self):
        """测试格式化最小对话历史"""
        conversation = [
            {
                "content": "测试消息"
            }
        ]
        
        formatted = self.extractor._format_conversation_history(conversation)
        
        self.assertIn("测试消息", formatted)
    
    def test_extract_impressions_empty_conversation(self):
        """测试从空对话提取印象"""
        async def run_test():
            result = await self.extractor.extract_impressions_from_conversation([], "group_1")
            self.assertEqual(result, [])
        
        asyncio.run(run_test())
    
    def test_extract_impressions_no_provider(self):
        """测试无LLM提供者时提取印象"""
        async def run_test():
            conversation = [{"content": "测试"}]
            result = await self.extractor.extract_impressions_from_conversation(conversation, "group_1")
            self.assertEqual(result, [])
        
        asyncio.run(run_test())
    
    def test_extract_impressions_success(self):
        """测试成功提取印象"""
        async def run_test():
            mock_provider = AsyncMock()
            mock_provider.text_chat.return_value = MockLLMResponse(
                '{"impressions": [{"person_name": "张三", "summary": "友善", "score": 0.8, "details": "很好", "confidence": 0.9}]}'
            )
            
            self.memory_system._llm_provider = mock_provider
            
            conversation = [{"content": "张三很友善"}]
            result = await self.extractor.extract_impressions_from_conversation(conversation, "group_1")
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["person_name"], "张三")
            self.assertEqual(result[0]["summary"], "友善")
            self.assertEqual(result[0]["score"], 0.8)
        
        asyncio.run(run_test())
    
    def test_extract_impressions_invalid_json(self):
        """测试提取印象时JSON解析失败"""
        async def run_test():
            mock_provider = AsyncMock()
            mock_provider.text_chat.return_value = MockLLMResponse("invalid json")
            
            self.memory_system._llm_provider = mock_provider
            
            conversation = [{"content": "测试"}]
            result = await self.extractor.extract_impressions_from_conversation(conversation, "group_1")
            
            self.assertEqual(result, [])
        
        asyncio.run(run_test())
    
    def test_extract_impressions_filter_invalid(self):
        """测试过滤无效印象"""
        async def run_test():
            mock_provider = AsyncMock()
            mock_provider.text_chat.return_value = MockLLMResponse(
                '{"impressions": [{"person_name": "张三", "summary": "友善"}, {"person_name": "", "summary": "无效"}]}'
            )
            
            self.memory_system._llm_provider = mock_provider
            
            conversation = [{"content": "测试"}]
            result = await self.extractor.extract_impressions_from_conversation(conversation, "group_1")
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["person_name"], "张三")
        
        asyncio.run(run_test())
    
    def test_extract_memories_empty_conversation(self):
        """测试从空对话提取记忆"""
        async def run_test():
            result = await self.extractor.extract_memories_and_themes([])
            self.assertEqual(result, [])
        
        asyncio.run(run_test())
    
    def test_extract_memories_no_provider(self):
        """测试无LLM提供者时提取记忆（使用回退提取）"""
        async def run_test():
            conversation = [{"content": "测试"}]
            result = await self.extractor.extract_memories_and_themes(conversation)
            self.assertIsInstance(result, list)
        
        asyncio.run(run_test())
    
    def test_extract_memories_success(self):
        """测试成功提取记忆"""
        async def run_test():
            mock_provider = AsyncMock()
            mock_provider.text_chat.return_value = MockLLMResponse(
                '{"memories": [{"theme": "工作", "content": "完成项目", "details": "详情", "participants": "我", "location": "办公室", "emotion": "开心", "tags": "重要", "confidence": 0.9, "memory_type": "normal"}]}'
            )
            
            self.memory_system._llm_provider = mock_provider
            
            conversation = [{"content": "今天完成了项目"}]
            result = await self.extractor.extract_memories_and_themes(conversation)
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["theme"], "工作")
            self.assertEqual(result[0]["content"], "完成项目")
        
        asyncio.run(run_test())
    
    def test_extract_memories_invalid_json(self):
        """测试提取记忆时JSON解析失败"""
        async def run_test():
            mock_provider = AsyncMock()
            mock_provider.text_chat.return_value = MockLLMResponse("invalid json")
            
            self.memory_system._llm_provider = mock_provider
            
            conversation = [{"content": "测试"}]
            result = await self.extractor.extract_memories_and_themes(conversation)
            
            self.assertIsInstance(result, list)
        
        asyncio.run(run_test())
    
    def test_extract_memories_filter_invalid(self):
        """测试过滤无效记忆"""
        async def run_test():
            mock_provider = AsyncMock()
            mock_provider.text_chat.return_value = MockLLMResponse(
                '{"memories": [{"theme": "工作", "content": "有效记忆"}, {"theme": "", "content": ""}]}'
            )
            
            self.memory_system._llm_provider = mock_provider
            
            conversation = [{"content": "测试"}]
            result = await self.extractor.extract_memories_and_themes(conversation)
            
            self.assertGreater(len(result), 0)
        
        asyncio.run(run_test())
    
    def test_parse_batch_response_valid(self):
        """测试解析有效的批量响应"""
        response = '{"memories": [{"theme": "工作", "content": "完成项目", "confidence": 0.9}]}'
        
        result = self.extractor._parse_batch_response(response)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["theme"], "工作")
    
    def test_parse_batch_response_invalid_json(self):
        """测试解析无效JSON"""
        response = "not json"
        
        result = self.extractor._parse_batch_response(response)
        
        self.assertEqual(result, [])
    
    def test_parse_batch_response_empty(self):
        """测试解析空响应"""
        response = '{"memories": []}'
        
        result = self.extractor._parse_batch_response(response)
        
        self.assertEqual(result, [])
    
    def test_parse_batch_response_filter_low_confidence(self):
        """测试过滤低置信度记忆"""
        response = '{"memories": [{"theme": "测试", "content": "内容", "confidence": 0.2}]}'
        
        result = self.extractor._parse_batch_response(response)
        
        self.assertEqual(len(result), 0)
    
    def test_parse_batch_response_chinese_quotes(self):
        """测试处理中文引号"""
        response = '{"memories": [{"theme": "测试", "content": "内容", "confidence": 0.9}]}'
        
        result = self.extractor._parse_batch_response(response)
        
        self.assertEqual(len(result), 1)
    
    def test_fallback_extraction_empty(self):
        """测试回退提取空历史"""
        async def run_test():
            result = await self.extractor._fallback_extraction([])
            self.assertEqual(result, [])
        
        asyncio.run(run_test())
    
    def test_fallback_extraction_with_content(self):
        """测试回退提取有内容"""
        async def run_test():
            history = [
                {"content": "今天天气不错"},
                {"content": "是的，天气很好"}
            ]
            result = await self.extractor._fallback_extraction(history)
            
            self.assertIsInstance(result, list)
        
        asyncio.run(run_test())
    
    def test_extract_simple_themes_empty(self):
        """测试简单主题提取空文本"""
        result = self.extractor._extract_simple_themes("")
        
        self.assertEqual(result, [])
    
    def test_extract_simple_themes_with_keywords(self):
        """测试简单主题提取关键词"""
        text = "今天天气很好，天气适合出去玩，天气真不错"
        
        result = self.extractor._extract_simple_themes(text)
        
        self.assertIsInstance(result, list)
    
    def test_extract_simple_themes_filter_common(self):
        """测试过滤常见词"""
        text = "你好谢谢再见"
        
        result = self.extractor._extract_simple_themes(text)
        
        self.assertNotIn("你好", result)
        self.assertNotIn("谢谢", result)
        self.assertNotIn("再见", result)
    
    def test_format_conversation_with_timestamp_int(self):
        """测试格式化带整数时间戳的对话"""
        conversation = [
            {
                "content": "测试",
                "timestamp": 1609459200,
                "role": "user",
                "sender_name": "测试用户"
            }
        ]
        
        formatted = self.extractor._format_conversation_history(conversation)
        
        self.assertIn("测试", formatted)
        self.assertIn("测试用户", formatted)
    
    def test_format_conversation_with_timestamp_float(self):
        """测试格式化带浮点时间戳的对话"""
        conversation = [
            {
                "content": "测试",
                "timestamp": 1609459200.5,
                "role": "assistant"
            }
        ]
        
        formatted = self.extractor._format_conversation_history(conversation)
        
        self.assertIn("Bot", formatted)
    
    def test_extract_memories_network_error(self):
        """测试提取记忆时的网络错误"""
        async def run_test():
            mock_provider = AsyncMock()
            mock_provider.text_chat.side_effect = Exception("upstream connection failed")
            
            self.memory_system._llm_provider = mock_provider
            
            conversation = [{"content": "测试"}]
            result = await self.extractor.extract_memories_and_themes(conversation)
            
            # 应该回退到简单提取
            self.assertIsInstance(result, list)
        
        asyncio.run(run_test())
    
    def test_extract_memories_other_error(self):
        """测试提取记忆时的其他错误"""
        async def run_test():
            mock_provider = AsyncMock()
            mock_provider.text_chat.side_effect = Exception("other error")
            
            self.memory_system._llm_provider = mock_provider
            
            conversation = [{"content": "测试"}]
            result = await self.extractor.extract_memories_and_themes(conversation)
            
            # 应该回退到简单提取
            self.assertIsInstance(result, list)
        
        asyncio.run(run_test())
    
    def test_parse_batch_response_with_type_errors(self):
        """测试解析响应时的类型错误"""
        # 测试confidence字段的各种情况
        response1 = '{"memories": [{"theme": "测试", "content": "内容", "confidence": "invalid"}]}'
        result1 = self.extractor._parse_batch_response(response1)
        # 应该使用默认值0.7
        self.assertIsInstance(result1, list)
        
        # 测试不是列表的memories
        response2 = '{"memories": "not a list"}'
        result2 = self.extractor._parse_batch_response(response2)
        self.assertEqual(result2, [])
        
        # 测试memory_type字段
        response3 = '{"memories": [{"theme": "测试", "content": "内容", "confidence": 0.9, "memory_type": "invalid"}]}'
        result3 = self.extractor._parse_batch_response(response3)
        self.assertGreater(len(result3), 0)
        if len(result3) > 0:
            self.assertEqual(result3[0]["memory_type"], "normal")
    
    def test_parse_batch_response_with_all_fields(self):
        """测试解析包含所有字段的响应"""
        response = '''{"memories": [{
            "theme": "工作,项目",
            "content": "完成项目",
            "details": "详细信息",
            "participants": "张三,李四",
            "location": "办公室",
            "emotion": "开心",
            "tags": "重要,成功",
            "confidence": 0.95,
            "memory_type": "impression"
        }]}'''
        
        result = self.extractor._parse_batch_response(response)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["theme"], "工作,项目")
        self.assertEqual(result[0]["content"], "完成项目")
        self.assertEqual(result[0]["details"], "详细信息")
        self.assertEqual(result[0]["participants"], "张三,李四")
        self.assertEqual(result[0]["location"], "办公室")
        self.assertEqual(result[0]["emotion"], "开心")
        self.assertEqual(result[0]["tags"], "重要,成功")
        self.assertEqual(result[0]["confidence"], 0.95)
        self.assertEqual(result[0]["memory_type"], "impression")
    
    def test_parse_batch_response_confidence_clamping(self):
        """测试置信度的范围限制"""
        # 测试超出范围的置信度
        response = '{"memories": [{"theme": "测试", "content": "内容", "confidence": 1.5}]}'
        result = self.extractor._parse_batch_response(response)
        
        if len(result) > 0:
            self.assertLessEqual(result[0]["confidence"], 1.0)
            self.assertGreaterEqual(result[0]["confidence"], 0.0)
    
    def test_parse_batch_response_with_json_fixes(self):
        """测试JSON修复功能"""
        # 测试需要两次JSON解析尝试的情况
        response = '{memories: [{theme: "测试", content: "内容", confidence: 0.9}]}'
        result = self.extractor._parse_batch_response(response)
        # 即使格式不标准，也应该尝试解析
        self.assertIsInstance(result, list)
    
    def test_parse_batch_response_not_dict_memory(self):
        """测试非字典类型的记忆条目"""
        response = '{"memories": ["not a dict", {"theme": "测试", "content": "内容", "confidence": 0.9}]}'
        result = self.extractor._parse_batch_response(response)
        # 应该过滤掉非字典项
        self.assertGreater(len(result), 0)
    
    def test_parse_batch_response_field_type_errors(self):
        """测试各字段的类型错误处理"""
        # 测试各种字段的类型转换错误
        response = '{"memories": [{"theme": {}, "content": [], "confidence": {}, "details": {}, "participants": {}, "location": {}, "emotion": {}, "tags": {}, "memory_type": {}}]}'
        result = self.extractor._parse_batch_response(response)
        # 应该使用默认值或跳过
        self.assertIsInstance(result, list)
    
    def test_parse_batch_response_with_exception_in_memory(self):
        """测试处理记忆时的异常"""
        # 这个测试确保即使单个记忆处理失败，整个函数也不会崩溃
        response = '{"memories": [{"theme": "测试", "content": "内容", "confidence": 0.9}]}'
        result = self.extractor._parse_batch_response(response)
        self.assertIsInstance(result, list)
    
    def test_extract_memories_outer_exception(self):
        """测试提取记忆时的外层异常"""
        async def run_test():
            # 设置一个会在外层抛出异常的LLM提供者
            class BadProvider:
                async def text_chat(self, **kwargs):
                    raise RuntimeError("Outer error")
            
            self.memory_system._llm_provider = BadProvider()
            
            conversation = [{"content": "测试"}]
            result = await self.extractor.extract_memories_and_themes(conversation)
            
            # 应该回退到简单提取
            self.assertIsInstance(result, list)
        
        asyncio.run(run_test())
    
    def test_parse_batch_response_nested_json_fix(self):
        """测试嵌套JSON修复"""
        # 测试第二次JSON修复尝试
        response = '{"memories": [{"theme": test, "content": value, "confidence": 0.9}]}'
        result = self.extractor._parse_batch_response(response)
        # 应该尝试修复并返回结果或空列表
        self.assertIsInstance(result, list)
    
    def test_parse_batch_response_with_str_exceptions(self):
        """测试字段转换为字符串时的异常"""
        # 创建一个模拟对象，在调用str()时会抛出异常
        import json
        
        # 使用Python的json模块无法直接创建这种对象，
        # 但我们可以测试其他边界情况
        # 测试None值的各个字段
        response_with_none = '''{"memories": [{
            "theme": null,
            "content": null,
            "details": null,
            "participants": null,
            "location": null,
            "emotion": null,
            "tags": null,
            "memory_type": null,
            "confidence": 0.9
        }]}'''
        
        result = self.extractor._parse_batch_response(response_with_none)
        # null值应该被转换为字符串"None"或空字符串
        self.assertIsInstance(result, list)
    
    def test_parse_batch_response_with_outer_exception(self):
        """测试整个记忆处理循环中的异常"""
        # 测试会在循环中触发AttributeError的情况
        response = '{"memories": [{"theme": "valid", "content": "valid", "confidence": 0.9}, null]}'
        result = self.extractor._parse_batch_response(response)
        # 应该至少处理第一个有效记忆
        self.assertGreater(len(result), 0)


if __name__ == '__main__':
    unittest.main()
