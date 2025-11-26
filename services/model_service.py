"""
通用模型服务接口
支持多种AI模型API提供商
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from PIL import Image
import io


class ModelAdapter(ABC):
    """模型适配器基类"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.kwargs = kwargs
    
    @abstractmethod
    async def generate_content(
        self,
        model: str,
        contents: List[Any],
        **kwargs
    ) -> str:
        """
        生成内容
        
        Args:
            model: 模型名称
            contents: 内容列表（可以是文本、图片等）
            **kwargs: 其他参数
            
        Returns:
            生成的文本内容
        """
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """检查API是否可用"""
        pass


class GeminiAdapter(ModelAdapter):
    """Google Gemini适配器"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(api_key, base_url, **kwargs)
        try:
            from google.genai import Client
            self.client = Client(api_key=api_key)
        except ImportError:
            raise ImportError("请安装 google-genai: pip install google-genai")
    
    async def generate_content(
        self,
        model: str,
        contents: List[Any],
        **kwargs
    ) -> str:
        """使用Gemini API生成内容"""
        try:
            response = await self.client.aio.models.generate_content(
                model=model,
                contents=contents,
                **kwargs
            )
            
            if not hasattr(response, 'candidates') or not response.candidates:
                raise ValueError("API响应被阻止或无效")
            
            if response.candidates and response.candidates[0].content.parts:
                return response.candidates[0].content.parts[0].text
            else:
                raise ValueError("API返回空响应")
        except Exception as e:
            raise Exception(f"Gemini API调用失败: {e}")
    
    async def is_available(self) -> bool:
        """检查Gemini API是否可用"""
        return self.client is not None


class OpenAIAdapter(ModelAdapter):
    """OpenAI适配器"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(api_key, base_url, **kwargs)
        try:
            import openai
            self.client = openai.AsyncOpenAI(
                api_key=api_key,
                base_url=base_url or "https://api.openai.com/v1"
            )
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")
    
    def _prepare_messages(self, contents: List[Any]) -> List[Dict[str, Any]]:
        """将内容转换为OpenAI格式的消息"""
        messages = []
        text_parts = []
        
        for content in contents:
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, Image.Image):
                # OpenAI支持图片，但需要转换为base64
                import base64
                buffered = io.BytesIO()
                content.save(buffered, format="PNG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                text_parts.append(f"[图片已包含]")
        
        if text_parts:
            messages.append({
                "role": "user",
                "content": "\n".join(text_parts)
            })
        
        return messages
    
    async def generate_content(
        self,
        model: str,
        contents: List[Any],
        **kwargs
    ) -> str:
        """使用OpenAI API生成内容"""
        try:
            messages = self._prepare_messages(contents)
            
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                **kwargs
            )
            
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("API返回空响应")
            
            return response.choices[0].message.content
        except Exception as e:
            raise Exception(f"OpenAI API调用失败: {e}")
    
    async def is_available(self) -> bool:
        """检查OpenAI API是否可用"""
        return self.client is not None


class AnthropicAdapter(ModelAdapter):
    """Anthropic Claude适配器"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(api_key, base_url, **kwargs)
        try:
            import anthropic
            self.client = anthropic.AsyncAnthropic(api_key=api_key)
        except ImportError:
            raise ImportError("请安装 anthropic: pip install anthropic")
    
    def _prepare_messages(self, contents: List[Any]) -> List[Dict[str, Any]]:
        """将内容转换为Claude格式的消息"""
        text_parts = []
        
        for content in contents:
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, Image.Image):
                # Claude支持图片，但需要转换为base64
                import base64
                buffered = io.BytesIO()
                content.save(buffered, format="PNG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                text_parts.append(f"[图片已包含]")
        
        return [{
            "role": "user",
            "content": "\n".join(text_parts)
        }]
    
    async def generate_content(
        self,
        model: str,
        contents: List[Any],
        **kwargs
    ) -> str:
        """使用Claude API生成内容"""
        try:
            messages = self._prepare_messages(contents)
            
            response = await self.client.messages.create(
                model=model,
                max_tokens=kwargs.get('max_tokens', 4096),
                messages=messages,
                **{k: v for k, v in kwargs.items() if k != 'max_tokens'}
            )
            
            if not response.content or not response.content[0].text:
                raise ValueError("API返回空响应")
            
            return response.content[0].text
        except Exception as e:
            raise Exception(f"Claude API调用失败: {e}")
    
    async def is_available(self) -> bool:
        """检查Claude API是否可用"""
        return self.client is not None


class CustomAPIAdapter(ModelAdapter):
    """自定义API适配器（支持OpenAI兼容的API）"""
    
    def __init__(self, api_key: str, base_url: str, **kwargs):
        if not base_url:
            raise ValueError("自定义API必须提供base_url")
        super().__init__(api_key, base_url, **kwargs)
        try:
            import openai
            self.client = openai.AsyncOpenAI(
                api_key=api_key,
                base_url=base_url
            )
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")
    
    def _prepare_messages(self, contents: List[Any]) -> List[Dict[str, Any]]:
        """将内容转换为OpenAI格式的消息"""
        messages = []
        text_parts = []
        
        for content in contents:
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, Image.Image):
                text_parts.append(f"[图片已包含]")
        
        if text_parts:
            messages.append({
                "role": "user",
                "content": "\n".join(text_parts)
            })
        
        return messages
    
    async def generate_content(
        self,
        model: str,
        contents: List[Any],
        **kwargs
    ) -> str:
        """使用自定义API生成内容"""
        try:
            messages = self._prepare_messages(contents)
            
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                **kwargs
            )
            
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("API返回空响应")
            
            return response.choices[0].message.content
        except Exception as e:
            raise Exception(f"自定义API调用失败: {e}")
    
    async def is_available(self) -> bool:
        """检查自定义API是否可用"""
        return self.client is not None


class ModelService:
    """通用模型服务"""
    
    def __init__(self):
        self.adapter: Optional[ModelAdapter] = None
        self.filter_model_name: Optional[str] = None
        self.verification_model_name: Optional[str] = None
    
    def initialize(
        self,
        provider: str,
        api_key: str,
        base_url: Optional[str] = None,
        filter_model: Optional[str] = None,
        verification_model: Optional[str] = None,
        **kwargs
    ):
        """
        初始化模型服务
        
        Args:
            provider: 提供商名称 (gemini, openai, claude, custom)
            api_key: API密钥
            base_url: API基础URL（自定义API必需）
            filter_model: 内容过滤模型名称
            verification_model: 验证问题生成模型名称
            **kwargs: 其他参数
        """
        provider = provider.lower()
        
        if provider == "gemini":
            self.adapter = GeminiAdapter(api_key, base_url, **kwargs)
            self.filter_model_name = filter_model or "gemini-2.5-flash"
            self.verification_model_name = verification_model or "gemini-2.5-flash-lite"
        elif provider == "openai":
            self.adapter = OpenAIAdapter(api_key, base_url, **kwargs)
            self.filter_model_name = filter_model or "gpt-4o-mini"
            self.verification_model_name = verification_model or "gpt-4o-mini"
        elif provider == "claude":
            self.adapter = AnthropicAdapter(api_key, base_url, **kwargs)
            self.filter_model_name = filter_model or "claude-3-haiku-20240307"
            self.verification_model_name = verification_model or "claude-3-haiku-20240307"
        elif provider == "custom":
            if not base_url:
                raise ValueError("自定义API必须提供base_url")
            self.adapter = CustomAPIAdapter(api_key, base_url, **kwargs)
            self.filter_model_name = filter_model
            self.verification_model_name = verification_model or filter_model
            if not self.filter_model_name:
                raise ValueError("自定义API必须提供filter_model")
        else:
            raise ValueError(f"不支持的提供商: {provider}")
    
    async def generate_content(
        self,
        model: str,
        contents: List[Any],
        **kwargs
    ) -> str:
        """生成内容"""
        if not self.adapter:
            raise ValueError("模型服务未初始化")
        return await self.adapter.generate_content(model, contents, **kwargs)
    
    async def is_available(self) -> bool:
        """检查服务是否可用"""
        if not self.adapter:
            return False
        return await self.adapter.is_available()


# 全局模型服务实例
model_service = ModelService()

