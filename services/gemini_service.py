from telegram import Message
from config import config
from services.model_service import model_service
import json
import random
import re
from PIL import Image
import io

LOCAL_VERIFICATION_QUESTIONS = [
    {"question": "中国的首都是哪里？", "correct_answer": "北京", "incorrect_answers": ["上海", "广州", "深圳"]},
    {"question": "一年有多少个月？", "correct_answer": "12", "incorrect_answers": ["10", "11", "13"]},
    {"question": "一周有多少天？", "correct_answer": "7", "incorrect_answers": ["5", "6", "8"]},
    {"question": "太阳从哪个方向升起？", "correct_answer": "东方", "incorrect_answers": ["西方", "南方", "北方"]},
    {"question": "水的化学式是什么？", "correct_answer": "H2O", "incorrect_answers": ["CO2", "O2", "NaCl"]},
    {"question": "地球上最大的海洋是哪个？", "correct_answer": "太平洋", "incorrect_answers": ["大西洋", "印度洋", "北冰洋"]},
    {"question": "哪个颜色是彩虹的第一种颜色？", "correct_answer": "红色", "incorrect_answers": ["橙色", "黄色", "绿色"]},
    {"question": "人体有多少个心脏？", "correct_answer": "1", "incorrect_answers": ["2", "3", "4"]},
    {"question": "哪个季节最热？", "correct_answer": "夏天", "incorrect_answers": ["春天", "秋天", "冬天"]},
    {"question": "哪个是最大的行星？", "correct_answer": "木星", "incorrect_answers": ["土星", "天王星", "海王星"]},
    {"question": "中国的国旗上有几颗星？", "correct_answer": "5", "incorrect_answers": ["3", "4", "6"]},
    {"question": "哪个是哺乳动物？", "correct_answer": "狗", "incorrect_answers": ["鱼", "鸟", "蛇"]},
    {"question": "哪个是水果？", "correct_answer": "苹果", "incorrect_answers": ["胡萝卜", "土豆", "洋葱"]},
    {"question": "哪个是交通工具？", "correct_answer": "汽车", "incorrect_answers": ["桌子", "椅子", "床"]},
    {"question": "哪个是颜色？", "correct_answer": "蓝色", "incorrect_answers": ["数字", "字母", "符号"]},
    {"question": "以下哪个不属于行星？", "correct_answer": "月亮", "incorrect_answers": ["地球", "火星", "金星"]},
    {"question": "以下哪个不属于水果？", "correct_answer": "胡萝卜", "incorrect_answers": ["苹果", "香蕉", "橙子"]},
    {"question": "以下哪个不属于交通工具？", "correct_answer": "房子", "incorrect_answers": ["汽车", "飞机", "火车"]},
    {"question": "以下哪个不属于颜色？", "correct_answer": "数字", "incorrect_answers": ["红色", "蓝色", "绿色"]},
    {"question": "以下哪个不属于哺乳动物？", "correct_answer": "鱼", "incorrect_answers": ["猫", "狗", "牛"]},
    {"question": "以下哪个不属于蔬菜？", "correct_answer": "苹果", "incorrect_answers": ["白菜", "萝卜", "黄瓜"]},
    {"question": "以下哪个不属于鸟类？", "correct_answer": "狗", "incorrect_answers": ["麻雀", "鸽子", "燕子"]},
    {"question": "以下哪个不属于金属？", "correct_answer": "木头", "incorrect_answers": ["铁", "铜", "铝"]},
    {"question": "以下哪个不属于饮料？", "correct_answer": "米饭", "incorrect_answers": ["水", "茶", "咖啡"]},
    {"question": "以下哪个不属于学习用品？", "correct_answer": "电视", "incorrect_answers": ["笔", "本子", "橡皮"]},
    {"question": "以下哪个不属于运动项目？", "correct_answer": "睡觉", "incorrect_answers": ["跑步", "游泳", "篮球"]},
    {"question": "以下哪个不属于季节？", "correct_answer": "星期", "incorrect_answers": ["春天", "夏天", "秋天"]},
    {"question": "以下哪个不属于方向？", "correct_answer": "上下", "incorrect_answers": ["东", "南", "西"]},
    {"question": "以下哪个不属于数字？", "correct_answer": "字母", "incorrect_answers": ["1", "2", "3"]}
]

class GeminiService:
    """AI服务类（保持向后兼容的命名）"""
    
    def __init__(self):
        self._initialize_model_service()
    
    def _initialize_model_service(self):
        """初始化模型服务"""
        api_key = config.AI_API_KEY
        
        if not api_key:
            model_service.adapter = None
            model_service.filter_model_name = None
            model_service.verification_model_name = None
            return
        
        try:
            model_service.initialize(
                provider=config.AI_PROVIDER,
                api_key=api_key,
                base_url=config.AI_BASE_URL,
                filter_model=config.AI_FILTER_MODEL,
                verification_model=config.AI_VERIFICATION_MODEL
            )
        except Exception as e:
            print(f"模型服务初始化失败: {e}")
            model_service.adapter = None
            model_service.filter_model_name = None
            model_service.verification_model_name = None
    
    @property
    def client(self):
        """向后兼容属性"""
        return model_service.adapter
    
    @property
    def filter_model_name(self):
        """向后兼容属性"""
        return model_service.filter_model_name
    
    @property
    def verification_model_name(self):
        """向后兼容属性"""
        return model_service.verification_model_name
    
    async def analyze_message(self, message: Message, image_bytes: bytes = None) -> dict:
        if not model_service.adapter or not model_service.filter_model_name or not config.ENABLE_AI_FILTER:
            return {"is_spam": False, "reason": "AI filter disabled"}

        content = []
        prompt_parts = [
            "你是一个内容审查员。你的任务是分析提供给你的文本和/或图片内容，并判断其是否包含垃圾信息、恶意软件、钓鱼链接、不当言论、辱骂、攻击性词语或任何违反安全政策的内容。",
            "请严格按照要求，仅以JSON格式返回你的分析结果，不要包含任何额外的解释或标记。",
            "**输出格式**: 你必须且只能以严格的JSON格式返回你的分析结果，不得包含任何解释性文字或代码块标记。",
            "**JSON结构**:\n```json\n{\n  \"is_spam\": boolean,\n  \"reason\": \"string\"\n}\n```\n*   `is_spam`: 如果内容违反**任何一条**安全策略，则为 `true`；如果内容完全安全，则为 `false`。\n*   `reason`: 用一句话精准概括判断依据。如果违规，请明确指出违规的类型。如果安全，此字段固定为 `\"内容未发现违规。\"`",
            "\n--- 以下是需要分析的内容 ---",
        ]

        if message.text:
            content.append(message.text)
        
        if image_bytes:
            try:
                image = Image.open(io.BytesIO(image_bytes))
                content.append(image)
            except Exception as e:
                print(f"Error processing image: {e}")

        if not content:
            return {"is_spam": False, "reason": "No content to analyze"}

        content.append("\n".join(prompt_parts))

        print(f"--- Sending request to {config.AI_PROVIDER.upper()} API ---")
        print(f"Model: {model_service.filter_model_name}")

        try:
            response_text = await model_service.generate_content(
                model=model_service.filter_model_name,
                contents=content
            )
            
            print(f"--- Received response from {config.AI_PROVIDER.upper()} API ---")
            print(f"Raw response: {response_text}")

            if not response_text:
                raise ValueError("API returned an empty response.")
            
            clean_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
            result = json.loads(clean_text)
            
            print(f"Parsed result: {result}")
            return result
        except json.JSONDecodeError as e:
            print(f"JSON解析失败: {e}")
            print(f"响应内容: {response_text if 'response_text' in locals() else 'N/A'}")
            return {"is_spam": False, "reason": "Analysis failed - JSON parse error"}
        except Exception as e:
            print(f"AI分析失败: {e}")
            return {"is_spam": False, "reason": "Analysis failed"}
    
    def _get_local_question(self) -> dict:
        question_data = random.choice(LOCAL_VERIFICATION_QUESTIONS)
        correct_answer = question_data['correct_answer']
        options = question_data['incorrect_answers'] + [correct_answer]
        random.shuffle(options)
        
        return {
            "question": question_data['question'],
            "correct_answer": correct_answer,
            "options": options
        }

    async def generate_unblock_question(self) -> dict:
        if not model_service.adapter or not model_service.verification_model_name:
            return self._get_local_question()

        prompt = """
        # 角色
        你是一个人机验证（CAPTCHA）问题生成器。
        # 任务
        生成一个随机的、适合成年人的中文常识性问题，用于区分人类和机器人。问题的格式应该是多样的。
        # 要求
        1.  **问题格式多样性**: 你需要随机选择以下两种问题格式之一进行提问：
            *   **a) 标准直接提问**: 例如，"中国的首都是哪里？"
            *   **b) 反向排除提问**: 使用"以下哪个不属于...？"或类似的句式。例如，"以下哪个不属于行星？"
        2.  **主题**: 问题主题应为完全随机的日常通用常识，无需限定在特定领域。
        3.  **难度**: 问题和选项的难度应设定为"绝大多数18岁以上母语为中文的成年人都能立即回答正确"的水平，避免专业或冷门知识。
        4.  **明确性**: 问题必须只有一个明确无误的正确答案。
        5.  **答案逻辑**:
            *   提供一个`correct_answer`（正确答案）。
            *   提供一个包含三个字符串的列表`incorrect_answers`（干扰项）。
            *   **对于标准问题**，所有选项应属于同一类别。
            *   **对于反向排除问题**，三个`incorrect_answers`应属于同一类别，而`correct_answer`则是那个不属于该类别的 outlier（局外者）。
        6.  **语言**: 所有内容必须为简体中文。
        7.  **输出格式**: 严格按照以下JSON格式返回，不要包含任何额外的解释或文字。
        # JSON格式示例
        {
          "question": "问题文本",
          "correct_answer": "正确答案",
          "incorrect_answers": ["干扰项1", "干扰项2", "干扰项3"]
        }
        """
        try:
            response_text = await model_service.generate_content(
                model=model_service.verification_model_name,
                contents=[prompt]
            )
            
            if not response_text:
                raise ValueError("API返回空响应")
            
            clean_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
            data = json.loads(clean_text)
            
            correct_answer = data['correct_answer']
            options = data['incorrect_answers'] + [correct_answer]
            random.shuffle(options)
            
            return {
                "question": data['question'],
                "correct_answer": correct_answer,
                "options": options
            }
        except Exception as e:
            print(f"生成解封验证问题失败: {e}")
            return self._get_local_question()

    async def generate_verification_challenge(self) -> dict:
        if not model_service.adapter or not model_service.verification_model_name:
            return self._get_local_question()

        prompt = """
        # 角色
        你是一个人机验证（CAPTCHA）问题生成器。
        # 任务
        生成一个随机的、适合成年人的中文常识性问题，用于区分人类和机器人。问题的格式应该是多样的。
        # 要求
        1.  **问题格式多样性**: 你需要随机选择以下两种问题格式之一进行提问：
            *   **a) 标准直接提问**: 例如，"中国的首都是哪里？"
            *   **b) 反向排除提问**: 使用"以下哪个不属于...？"或类似的句式。例如，"以下哪个不属于行星？"
        2.  **主题**: 问题主题应为完全随机的日常通用常识，无需限定在特定领域。
        3.  **难度**: 问题和选项的难度应设定为"绝大多数18岁以上母语为中文的成年人都能立即回答正确"的水平，避免专业或冷门知识。
        4.  **明确性**: 问题必须只有一个明确无误的正确答案。
        5.  **答案逻辑**:
            *   提供一个`correct_answer`（正确答案）。
            *   提供一个包含三个字符串的列表`incorrect_answers`（干扰项）。
            *   **对于标准问题**，所有选项应属于同一类别。
            *   **对于反向排除问题**，三个`incorrect_answers`应属于同一类别，而`correct_answer`则是那个不属于该类别的 outlier（局外者）。
        6.  **语言**: 所有内容必须为简体中文。
        7.  **输出格式**: 严格按照以下JSON格式返回，不要包含任何额外的解释或文字。
        # JSON格式示例
        {
          "question": "问题文本",
          "correct_answer": "正确答案",
          "incorrect_answers": ["干扰项1", "干扰项2", "干扰项3"]
        }
        """
        try:
            response_text = await model_service.generate_content(
                model=model_service.verification_model_name,
                contents=[prompt]
            )
            
            if not response_text:
                raise ValueError("API返回空响应")

            clean_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
            data = json.loads(clean_text)
            
            correct_answer = data['correct_answer']
            options = data['incorrect_answers'] + [correct_answer]
            random.shuffle(options)
            
            return {
                "question": data['question'],
                "correct_answer": correct_answer,
                "options": options
            }
        except Exception as e:
            print(f"生成验证问题失败: {e}")
            return self._get_local_question()

    async def generate_autoreply(self, user_message: str, knowledge_base_content: str) -> str:
        if not model_service.adapter or not model_service.filter_model_name:
            return None

        if not knowledge_base_content or knowledge_base_content.strip() == "":
            return None

        prompt_parts = [
            "你是一个客服助手，必须严格根据提供的知识库内容来回答用户的问题。",
            "**重要规则：**",
            "1. 你只能根据知识库中的内容来回答用户的问题。",
            "2. 如果知识库中没有相关内容，你必须明确告诉用户：'抱歉，我无法根据现有知识库回答您的问题，请稍后管理员会为您回复。'",
            "3. 严禁编造、猜测或提供知识库中没有的信息。",
            "4. 如果用户的问题与知识库内容相关，请整理汇总相关知识库条目，用清晰、友好的语言回答。",
            "5. 回答要简洁明了，直接回答用户的问题。",
            "6. **重要：请使用Markdown格式回复**，可以使用以下Markdown语法：",
            "   - 使用 **粗体** 强调重要内容",
            "   - 使用 *斜体* 表示次要信息",
            "   - 使用 `代码` 格式表示技术术语或命令",
            "   - 使用列表格式（- 或 1.）组织内容",
            "   - 使用 > 引用块表示重要提示",
            "\n--- 知识库内容 ---",
            knowledge_base_content,
            "\n--- 用户问题 ---",
            user_message,
            "\n--- 请根据知识库内容回答用户问题（使用Markdown格式）---",
            "如果知识库中没有相关内容，请回复：'抱歉，我无法根据现有知识库回答您的问题，请稍后管理员会为您回复。'"
        ]

        try:
            response_text = await model_service.generate_content(
                model=model_service.filter_model_name,
                contents=["\n".join(prompt_parts)]
            )
            
            if not response_text:
                return None
            
            if "无法根据现有知识库" in response_text or "抱歉" in response_text:
                return None
            
            return response_text.strip()
        except Exception as e:
            print(f"自动回复生成失败: {e}")
            return None

gemini_service = GeminiService()
