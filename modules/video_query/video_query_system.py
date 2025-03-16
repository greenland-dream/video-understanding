import yaml
from typing import List, Dict, Any, Optional, ClassVar, Set
from pydantic import BaseModel, Field, field_validator
import json
import os
from pathlib import Path
import time
import re
from utils.log_config import setup_logger

import chromadb
from db.video_db import VideoDatabase
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
# from langchain_core.pydantic_v1 import BaseModel, Field, validator
from pydantic import BaseModel, Field, field_validator
# 导入本地模型接口
from modules.call_qwenQwQ import generate_response
from modules.call_rerank_api import call_rerank_api
from modules.call_parse_api import call_parse_api

# Get logger using module name as identifier
logger = setup_logger(__name__)

# 查询解析模型
class VideoQueryIntent(BaseModel):
    """解析用户查询为结构化搜索意图"""
    description_query: Optional[str] = Field(None, description="与视频内容/视觉描述相关的查询部分")
    transcript_query: Optional[str] = Field(None, description="与对话/旁白相关的查询部分")
    metadata_filters: Dict[str, str] = Field(default_factory=dict, description="元数据过滤条件，如地点、时间等")
    limit: int = Field(default=20, description="返回结果数量上限")
    search_mode: str = Field(default="auto", description="搜索模式: 'description_only', 'transcript_only', 'or', 'and', 'auto'")
    
    # 可接受的元数据值定义（保持中文值以便于搜索）
    VALID_TIME_PERIODS: ClassVar[Set[str]] = {"白天", "晚上"}
    VALID_COLORS: ClassVar[Set[str]] = {"红色", "橙色", "黄色", "绿色", "蓝色", "黑色", "白色", "灰色"}
    VALID_ORIENTATIONS: ClassVar[Set[str]] = {"横屏", "竖屏", "方屏"}
    VALID_SEARCH_MODES: ClassVar[Set[str]] = {"description_only", "transcript_only", "or", "and", "auto"}
    
    @field_validator("limit")
    @classmethod
    def limit_range(cls, v):
        if v < 1:
            return 20
        if v > 100:
            return 100
        return v
    
    @field_validator("search_mode")
    @classmethod
    def validate_search_mode(cls, v):
        if v not in cls.VALID_SEARCH_MODES:
            return "auto"
        return v
    
    @field_validator("metadata_filters")
    @classmethod
    def validate_metadata_filters(cls, v):
        # 验证元数据过滤条件
        # 拍摄时间验证
        if "time_of_day" in v and v["time_of_day"] not in cls.VALID_TIME_PERIODS:
            v["time_of_day"] = "白天"  # 默认为白天
        
        # 颜色验证
        if "color" in v and v["color"] not in cls.VALID_COLORS:
            v.pop("color")  # 如果不是有效颜色，则移除该过滤条件
        
        # 视频尺寸验证
        if "orientation" in v and v["orientation"] not in cls.VALID_ORIENTATIONS:
            v.pop("orientation")  # 如果不是有效尺寸，则移除该过滤条件
        
        # date格式应为"xxxx年xx月"，但这里不做严格验证
        # duration是数字，单位为秒，也不做严格验证
                
        return v

class VideoQuerySystem:
    def __init__(self, db_path: str, chroma_path: str, config_path: str = "config/model_config.yaml"):
        """
        初始化视频查询系统
        
        参数:
            db_path: SQLite 数据库路径
            chroma_path: ChromaDB 向量数据库路径
            config_path: 模型配置文件路径
        """
        # 初始化数据库
        self.db = VideoDatabase(db_path, chroma_path)
        
        # 加载模型配置
        self.config = self._load_config(config_path)
        self.model_config = self.config.get("query_system", {})
        
        # 加载提示模板
        self.query_parser_template = self._load_prompt_template("config/prompts/query_parser.md")
        self.rerank_template = self._load_prompt_template("config/prompts/reranking.md")
        self.transcript_rerank_template = self._load_prompt_template("config/prompts/transcript_reranking.md")
        
        # 设置查询解析器的提示模板
        self.query_parser_prompt = PromptTemplate(
            template=self.query_parser_template,
            input_variables=["query"],
            partial_variables={"format_instructions": PydanticOutputParser(pydantic_object=VideoQueryIntent).get_format_instructions()}
        )
        
        # 设置重排序提示模板
        self.rerank_prompt = PromptTemplate(
            template=self.rerank_template,
            input_variables=["query", "video_descriptions"]
        )
        
        # 设置对话重排序提示模板
        self.transcript_rerank_prompt = PromptTemplate(
            template=self.transcript_rerank_template,
            input_variables=["query", "video_descriptions"]
        )
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """从YAML文件加载模型配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            print(f"加载配置文件出错: {e}")
            return {}
    
    def _load_prompt_template(self, template_path: str) -> str:
        """从文件加载提示模板"""
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            return template
        except Exception as e:
            print(f"加载提示模板出错 {template_path}: {e}")
            # 返回默认模板
            if "query_parser" in template_path:
                return """
                你是一个帮助解析视频搜索查询的AI助手。
                
                基于用户的查询: "{query}"
                
                请提取以下信息:
                1. 描述查询：与视频视觉内容相关的部分
                2. 对话查询：与对话、旁白或声音相关的部分（如果有）
                3. 元数据过滤器：任何特定的元数据要求，如拍摄地点、拍摄时间、日期等
                
                {format_instructions}
                """
            else:
                return """
                你是一个视频推荐系统。基于用户的查询，对以下视频按照与查询的相关性进行排序。返回按相关性排序的视频ID列表。
                
                用户查询: {query}
                
                视频描述:
                {video_descriptions}
                
                只返回按相关性排序的视频ID列表，用逗号分隔，不要给出任何解释。
                """
    
    def _call_local_model(self, prompt: str) -> str:
        """调用本地MLX模型处理提示文本"""
        try:
            model_path = self.model_config.get("model", "mlx-community/Qwen2.5-7B-Instruct-1M-3bit")
            max_tokens = self.model_config.get("max_tokens", 2048)
            temperature = self.model_config.get("temperature", 0.0)
            
            response = generate_response(
                model_path=model_path,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                verbose=True
            )
            
            return response
        except Exception as e:
            print(f"调用本地模型出错: {e}")
            return ""
    
    def parse_query(self, query: str, use_api: bool = True) -> VideoQueryIntent:
        """
        Parse user query into structured search intent
        
        Args:
            query: User's natural language query
            use_api: Whether to try using remote API first (default: True)
            
        Returns:
            VideoQueryIntent object with structured search parameters
        """
        # Format prompt text
        prompt = self.query_parser_prompt.format(query=query)
        
        # Try using remote API first if enabled
        if use_api:
            try:
                logger.info("尝试使用远程API进行查询解析")
                format_instructions = PydanticOutputParser(pydantic_object=VideoQueryIntent).get_format_instructions()
                response = call_parse_api(
                    provider=None,  # 使用优先级自动选择提供商
                    query=query,
                    prompt_file="query_parser.md",
                    format_instructions=format_instructions,
                    timeout=60  # 设置API超时时间
                )
                logger.info("使用远程API进行查询解析成功")
            except Exception as e:
                # If remote API fails, fall back to local model
                logger.warning(f"远程API查询解析失败，回退到本地模型: {e}")
                response = self._call_local_model(prompt)
                logger.info("使用本地模型进行查询解析成功")
        else:
            # Call local model directly
            response = self._call_local_model(prompt)
        
        # Extract JSON from response
        try:
            # Try to find JSON object in response
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Look for any JSON-like structure
                json_match = re.search(r'(\{.*\})', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    raise ValueError("No JSON found in response")
            
            # Parse JSON
            parsed_data = json.loads(json_str)
            
            # Handle "unspecified" values, convert them to None
            transcript_query = parsed_data.get("transcript_query")
            if transcript_query == "未指定":
                transcript_query = None
                
            # Handle description query that might also be unspecified
            description_query = parsed_data.get("description_query")
            if description_query == "未指定":
                description_query = None
            
            # Determine search mode if not explicitly specified
            search_mode = parsed_data.get("search_mode", "auto")
            if search_mode == "auto":
                # Auto-determine search mode based on queries
                if description_query and transcript_query:
                    search_mode = "and"  # Default to AND when both are present
                elif description_query:
                    search_mode = "description_only"
                elif transcript_query:
                    search_mode = "transcript_only"
                else:
                    # If neither is specified, default to description search with original query
                    description_query = query
                    search_mode = "description_only"
            
            # Create VideoQueryIntent object
            intent = VideoQueryIntent(
                description_query=description_query,
                transcript_query=transcript_query,
                metadata_filters=parsed_data.get("metadata_filters", {}),
                limit=parsed_data.get("limit", 20),
                search_mode=search_mode
            )
            return intent
        except Exception as e:
            logger.error(f"Error parsing model response: {e}")
            logger.debug(f"Original response: {response}")
            # Fallback: use entire query as description query
            return VideoQueryIntent(
                description_query=query,
                transcript_query=None,
                metadata_filters={},
                limit=20,
                search_mode="description_only"
            )
    def search_videos(self, query: str, use_api_for_parsing: bool = True, use_api_for_reranking: bool = True) -> List[Dict[str, Any]]:
        """
        搜索匹配给定查询的视频
        
        参数:
            query: 自然语言视频查询
            use_api_for_parsing: 是否使用远程API进行查询解析 (默认: True)
            use_api_for_reranking: 是否使用远程API进行结果重排序 (默认: True)
            
        返回:
            按相关性排序的视频元数据列表
        """
        # 步骤1: 解析查询以理解搜索意图
        intent = self.parse_query(query, use_api=use_api_for_parsing)
        logger.info(f"解析的查询意图: {intent}")
        
        # 初始化结果变量
        description_results = []
        transcript_results = []
        final_results = []
        
        # 步骤2: 根据搜索模式执行检索
        # 如果需要描述搜索
        if intent.search_mode in ["description_only", "or", "and", "auto"] and intent.description_query:
            description_results = self._knowledge_enhanced_search(intent.description_query)
            logger.info(f"描述搜索结果数量: {len(description_results)}")
        
        # 如果需要对话搜索
        if intent.search_mode in ["transcript_only", "or", "and", "auto"] and intent.transcript_query:
            transcript_results = self._search_by_transcript(intent.transcript_query)
            logger.info(f"对话搜索结果数量: {len(transcript_results)}")
        
        # 步骤3: 根据搜索模式合并结果
        if intent.search_mode == "description_only":
            final_results = description_results
        elif intent.search_mode == "transcript_only":
            final_results = transcript_results
        elif intent.search_mode == "or":
            # 合并结果 (取并集)
            final_results = self._merge_results(description_results, transcript_results)
        elif intent.search_mode == "and":
            # 取交集
            final_results = self._intersect_results(description_results, transcript_results)
        else:  # auto 模式
            if description_results and transcript_results:
                # 如果两种搜索都有结果，取交集
                final_results = self._intersect_results(description_results, transcript_results)
                # 如果交集为空，则取并集
                if not final_results:
                    final_results = self._merge_results(description_results, transcript_results)
            elif description_results:
                final_results = description_results
            elif transcript_results:
                final_results = transcript_results
        
        # 步骤4: 应用元数据过滤
        # if intent.metadata_filters:
        #     filtered_results = []
        #     for result in final_results:
        #         if self._match_metadata_filters(result['metadata'], intent.metadata_filters):
        #             filtered_results.append(result)
        #     final_results = filtered_results
        
        # 步骤5: 必要时重新排序结果
        if len(final_results) > intent.limit:
            reranked_results = self._rerank_results(final_results, intent, use_api=use_api_for_reranking)
            return reranked_results[:intent.limit]
        
        return final_results[:intent.limit]
    
    def _expand_query(self, query: str) -> str:
        """
        将简短查询扩展为更丰富的描述，以提高语义匹配率
        
        参数:
            query: 原始查询语句
            
        返回:
            扩展后的查询语句
        """
        # 使用本地语言模型扩展查询
        system_prompt = """你是一个查询扩展专家。用户会提供简短的视频查询关键词，你需要将其扩展为更详细的描述，
包括可能的场景、环境、物体和氛围等细节，以便更好地匹配视频描述。
只返回扩展后的描述，不要有任何前缀或解释。保留原始查询的关键内容，但用更丰富的语言表达。"""
        
        prompt = f"将以下视频查询扩展为详细描述：{query}"
        
        try:
            # 使用本地模型扩展查询
            expanded_query = self._call_local_model(f"{system_prompt}\n\n{prompt}")
            
            # 如果扩展结果过短或没有明显变化，则使用原始查询
            if len(expanded_query) < len(query) * 1.5 or expanded_query.strip() == query.strip():
                return query
            
            # 将原始查询和扩展查询组合，确保关键术语得到保留
            combined_query = f"{query} {expanded_query}"
            return combined_query
        except Exception as e:
            print(f"查询扩展失败: {str(e)}")
            return query  # 返回原始查询

    def _search_by_description(self, description_query: str, n_results: int = 200) -> List[Dict[str, Any]]:
        """通过描述搜索视频"""
        # 扩展查询以提高语义匹配率
        expanded_query = self._expand_query(description_query)
        print(f"原始查询: \"{description_query}\"")
        print(f"扩展查询: \"{expanded_query}\"")
        
        # 直接访问Chroma集合作为低级操作
        results = self.db.collection.query(
            query_texts=[expanded_query],
            n_results=n_results,
            where={"document_type": "description"}
        )
        
        # 格式化结果
        formatted_results = []
        for i, (id, metadata, score) in enumerate(zip(
            results.get('ids', [[]])[0],
            results.get('metadatas', [[]])[0],
            results.get('distances', [[]])[0]
        )):
            formatted_results.append({
                'id': id,
                'video_path': metadata.get('video_path'),
                'metadata': metadata,
                'description_score': 1.0 - score,  # 将距离转换为相似度分数
            })
        
        return formatted_results
    
    def _search_by_transcript(self, transcript_query: str, n_results: int = 100) -> List[Dict[str, Any]]:
        """通过对话内容搜索视频"""
        results = self.db.collection.query(
            query_texts=[transcript_query],
            n_results=n_results,
            where={"document_type": "transcript"}
        )
        
        # 格式化结果
        formatted_results = []
        for i, (id, metadata, score) in enumerate(zip(
            results.get('ids', [[]])[0],
            results.get('metadatas', [[]])[0],
            results.get('distances', [[]])[0]
        )):
            # 计算相似度分数 (1 - 距离)
            similarity = 1.0 - score
            
            # 去掉'_transcript'后缀以获取原始视频ID
            original_id = id.replace('_transcript', '')
            
            # 获取对话内容
            transcript = results["documents"][0][i] if "documents" in results and len(results["documents"]) > 0 else ""
            
            formatted_results.append({
                'id': original_id,
                'video_path': metadata.get('video_path'),
                'metadata': metadata,
                'transcript': transcript,  # 添加对话内容
                'transcript_score': similarity,  # 确保使用标准化的字段名
                'similarity': similarity,  # 保持一致性
                'source': 'transcript'
            })
        
        return formatted_results
    
    def _apply_metadata_filters(
        self, 
        description_results: List[Dict[str, Any]], 
        transcript_results: Optional[List[Dict[str, Any]]] = None,
        filters: Dict[str, str] = None
    ) -> List[Dict[str, Any]]:
        """
        应用元数据过滤并组合描述和对话搜索结果
        
        如果提供了transcript_results，则取结果交集。
        """
        # 如果没有对话结果，只过滤描述结果
        if not transcript_results:
            if not filters:
                return description_results
            
            # 应用元数据过滤
            filtered_results = []
            for result in description_results:
                if self._match_metadata_filters(result['metadata'], filters):
                    filtered_results.append(result)
            return filtered_results
        
        # 如果有对话结果，需要取交集
        description_dict = {r['id']: r for r in description_results}
        transcript_dict = {r['id']: r for r in transcript_results}
        
        # 查找共同ID
        common_ids = set(description_dict.keys()) & set(transcript_dict.keys())
        
        # 组合结果
        combined_results = []
        for id in common_ids:
            desc_result = description_dict[id]
            trans_result = transcript_dict[id]
            
            # 如果元数据过滤器不匹配则跳过
            if filters and not self._match_metadata_filters(desc_result['metadata'], filters):
                continue
            
            # 组合分数（简单平均）
            combined_score = (desc_result.get('description_score', 0) + 
                              trans_result.get('transcript_score', 0)) / 2
            
            combined_results.append({
                **desc_result,
                'transcript_score': trans_result.get('transcript_score', 0),
                'combined_score': combined_score
            })
        
        # 按组合分数排序
        return sorted(combined_results, key=lambda x: x.get('combined_score', 0), reverse=True)
    
    def _match_metadata_filters(self, metadata: Dict[str, Any], filters: Dict[str, str]) -> bool:
        """检查元数据是否匹配所有过滤器"""
        if not filters:
            return True
            
        for key, value in filters.items():
            # 跳过值为"未指定"的过滤条件
            if value == "未指定":
                continue
                
            # 如果元数据中没有该字段则跳过
            if key not in metadata:
                return False
            
            filter_value = str(value).lower()
            metadata_value = str(metadata[key]).lower()
            
            # 使用简单的包含匹配逻辑，因为现在值已标准化
            if filter_value not in metadata_value:
                return False
                
        return True
    
    def _rerank_results(self, results: List[Dict[str, Any]], intent: VideoQueryIntent, use_api: bool = True) -> List[Dict[str, Any]]:
        """
        使用本地LLM或远程API重新排序结果以更好地匹配查询意图
        
        参数:
            results: 要重排序的结果列表
            intent: 查询意图对象
            use_api: 是否使用远程API进行重排序 (默认: True)
        
        返回:
            重排序后的结果列表
        """
        if not results:
            return []
            
        # 准备视频描述
        descriptions = []
        id_to_result = {}
        for i, result in enumerate(results):  # 限制为50个以避免token限制
            id_to_result[str(i)] = result
            
            # 简化描述，只包含最相关的信息
            description = f"视频 {i}:\n"
            
            # 添加描述内容
            if 'document' in result:
                description += f"描述: {result.get('document', '')}\n"
            elif 'description' in result:
                description += f"描述: {result.get('description', '')}\n"
            
            # 如果是对话搜索，添加对话内容
            if intent.search_mode == "transcript_only" or intent.transcript_query:
                # 从数据库获取对话内容
                video_path = result.get('video_path', '')
                if video_path:
                    transcript = self._get_transcript_for_video(video_path)
                    if transcript:
                        description += f"对话内容: {transcript}\n"
                        # 将对话内容添加到结果中，以便在显示结果时使用
                        result['transcript'] = transcript
            
            # 添加可能有助于排序的关键元数据（如果确实需要）
            metadata = result['metadata']
            if 'scene' in metadata and metadata['scene']:
                description += f"场景: {metadata['scene']}\n"
            
            descriptions.append(description)
        
        # 构建重排序查询
        rerank_query = ""
        
        # 根据搜索模式构建查询
        if intent.search_mode == "description_only" and intent.description_query:
            rerank_query = f"视频内容: {intent.description_query}"
        elif intent.search_mode == "transcript_only" and intent.transcript_query:
            rerank_query = f"视频对话: {intent.transcript_query}"
        elif intent.search_mode == "and" and intent.description_query and intent.transcript_query:
            rerank_query = f"视频内容: {intent.description_query} 并且包含对话: {intent.transcript_query}"
        elif intent.search_mode == "or" and intent.description_query and intent.transcript_query:
            rerank_query = f"视频内容: {intent.description_query} 或者包含对话: {intent.transcript_query}"
        else:
            # 自动模式或其他情况
            if intent.description_query:
                rerank_query += f"视频内容: {intent.description_query} "
            if intent.transcript_query:
                rerank_query += f"视频对话: {intent.transcript_query}"
            if not rerank_query:
                # 如果没有有效查询，使用原始查询
                rerank_query = "请根据视频内容相关性排序"
        
        # 选择合适的重排序提示模板
        prompt_file = "reranking.md"
        prompt_template = self.rerank_prompt
        if intent.search_mode == "transcript_only" or (intent.transcript_query and not intent.description_query):
            prompt_file = "transcript_reranking.md"
            prompt_template = self.transcript_rerank_prompt
        
        # 格式化提示用于本地模型
        prompt = prompt_template.format(
            query=rerank_query,
            video_descriptions="\n\n".join(descriptions)
        )
        
        # 根据use_api参数决定是否使用远程API
        if use_api:
            # 尝试使用远程API进行重排序
            try:
                # 首先尝试使用远程API
                video_descriptions_str = "\n\n".join(descriptions)
                logger.info("尝试使用远程API进行重排序")
                response = call_rerank_api(
                    provider=None,  # 使用优先级自动选择提供商
                    query=rerank_query,
                    video_descriptions=video_descriptions_str,
                    prompt_file=prompt_file,  # 使用选择的提示模板
                    timeout=100  # 设置API超时时间
                )
                logger.info("使用远程API进行重排序成功")
            except Exception as e:
                # 如果远程API失败，回退到本地模型
                logger.warning(f"远程API重排序失败，回退到本地模型: {e}")
                response = self._call_local_model(prompt)
                logger.info("使用本地模型进行重排序成功")
        else:
            # 直接使用本地模型
            logger.info("直接使用本地模型进行重排序")
            response = self._call_local_model(prompt)
        
        # 解析重排序后的ID
        try:
            reranked_ids = [id.strip() for id in response.split(',')]
            reranked_results = []
            
            # 创建重排序后的结果列表，保留原始分数
            for id in reranked_ids:
                if id in id_to_result:
                    # 复制原始结果以保留所有字段
                    reranked_result = id_to_result[id].copy()
                    
                    # 根据搜索模式正确设置相似度分数字段
                    if intent.search_mode == "transcript_only":
                        # 对于纯对话搜索，确保只设置transcript_score
                        if 'similarity' in reranked_result and 'transcript_score' not in reranked_result:
                            reranked_result['transcript_score'] = reranked_result['similarity']
                        # 确保不设置description_score
                        if 'description_score' in reranked_result:
                            del reranked_result['description_score']
                    elif intent.search_mode == "description_only":
                        # 对于纯描述搜索，确保只设置description_score
                        if 'similarity' in reranked_result and 'description_score' not in reranked_result:
                            reranked_result['description_score'] = reranked_result['similarity']
                        # 确保不设置transcript_score
                        if 'transcript_score' in reranked_result:
                            del reranked_result['transcript_score']
                    else:
                        # 对于混合搜索，保留两种分数
                        if 'similarity' in reranked_result:
                            if 'source' in reranked_result and reranked_result['source'] == 'transcript':
                                if 'transcript_score' not in reranked_result:
                                    reranked_result['transcript_score'] = reranked_result['similarity']
                            elif 'source' in reranked_result and reranked_result['source'] == 'description':
                                if 'description_score' not in reranked_result:
                                    reranked_result['description_score'] = reranked_result['similarity']
                    
                    # 添加到重排序结果列表
                    reranked_results.append(reranked_result)
            
            # 添加任何未重排序的结果
            remaining_results = [r for r in results if str(results.index(r)) not in reranked_ids]
            return reranked_results + remaining_results
        except Exception as e:
            logger.error(f"解析重排序结果出错: {e}")
            return results
    
    def _get_transcript_for_video(self, video_path: str) -> str:
        """
        获取视频的对话内容
        
        参数:
            video_path: 视频文件路径
            
        返回:
            视频的对话内容，如果没有则返回空字符串
        """
        try:
            # 查询数据库获取对话内容
            results = self.db.collection.query(
                query_texts=[""],  # 空查询，只用于获取文档
                n_results=1,
                where={"$and": [
                    {"document_type": "transcript"},
                    {"video_path": video_path}
                ]}
            )
            
            # 如果找到结果，返回第一个文档
            if results and results.get('documents') and results['documents'][0]:
                return results['documents'][0][0]
            
            return ""
        except Exception as e:
            logger.error(f"获取视频对话内容出错: {e}")
            return ""
    
    def close(self):
        """关闭数据库连接"""
        self.db.close()

    def _knowledge_enhanced_search(self, query: str, n_results: int = 50) -> List[Dict[str, Any]]:
        """
        知识增强的检索方法
        
        参数:
            query: 用户查询
            n_results: 返回结果数量上限
            
        返回:
            检索结果列表
        """
        # 使用查询进行检索
        results = self.db.collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"document_type": "description"}
        )
        
        # 格式化结果
        formatted_results = []
        for i, (id, metadata, score) in enumerate(zip(
            results["ids"][0], 
            results["metadatas"][0], 
            results["distances"][0]
        )):
            # 计算相似度分数 (1 - 距离)
            similarity = 1.0 - score
            
            # 确保只处理描述类型的文档
            if metadata.get("document_type") == "description":
                # 获取原始视频路径和文档内容
                video_path = metadata.get("video_path", "")
                document = results["documents"][0][i]
                
                # 格式化结果
                formatted_result = {
                    "id": id,
                    "video_path": video_path,
                    "similarity": similarity,
                    "description_score": similarity,  # 添加标准化的描述分数字段
                    "description": document,
                    "metadata": metadata,
                    "source": "description"
                }
                formatted_results.append(formatted_result)
        
        return formatted_results
        
    def _merge_results(self, results1: List[Dict[str, Any]], results2: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并两个结果列表，根据视频路径去重
        
        参数:
            results1: 第一个结果列表 (通常是描述搜索结果)
            results2: 第二个结果列表 (通常是对话搜索结果)
            
        返回:
            合并后的结果列表，按相似度排序
        """
        # 如果任一列表为空，返回另一个列表
        if not results1:
            return results2
        if not results2:
            return results1
            
        # 使用字典进行去重
        merged_dict = {}
        
        # 处理第一个结果列表 (通常是描述搜索结果)
        for result in results1:
            video_path = result["video_path"]
            
            # 标准化分数字段
            score = result.get("similarity", 0)
            if "description_score" in result:
                score = result.get("description_score", 0)
                
            result_copy = result.copy()
            result_copy["description_score"] = score
            result_copy["source"] = result.get("source", "description")
            
            merged_dict[video_path] = result_copy
        
        # 处理第二个结果列表 (通常是对话搜索结果)
        for result in results2:
            video_path = result["video_path"]
            
            # 标准化分数字段
            score = result.get("similarity", 0)
            if "transcript_score" in result:
                score = result.get("transcript_score", 0)
                
            if video_path not in merged_dict:
                # 如果是新视频，直接添加
                result_copy = result.copy()
                result_copy["transcript_score"] = score
                result_copy["source"] = result.get("source", "transcript")
                merged_dict[video_path] = result_copy
            else:
                # 如果已存在，更新相似度分数
                existing = merged_dict[video_path]
                existing["transcript_score"] = score
                
                # 计算组合分数 (加权平均)
                desc_score = existing.get("description_score", 0)
                trans_score = score
                combined_score = (desc_score * 0.6) + (trans_score * 0.4)  # 给描述搜索更高权重
                existing["combined_score"] = combined_score
                
                # 更新来源信息
                existing["source"] = f"{existing['source']},{result.get('source', 'transcript')}"
        
        # 为所有结果计算组合分数
        for path, result in merged_dict.items():
            if "combined_score" not in result:
                if "description_score" in result and "transcript_score" in result:
                    # 如果有两种分数，计算加权平均
                    result["combined_score"] = (result["description_score"] * 0.6) + (result["transcript_score"] * 0.4)
                elif "description_score" in result:
                    # 如果只有描述分数
                    result["combined_score"] = result["description_score"]
                elif "transcript_score" in result:
                    # 如果只有对话分数
                    result["combined_score"] = result["transcript_score"]
                else:
                    # 默认分数
                    result["combined_score"] = result.get("similarity", 0)
        
        # 将字典值转换回列表并按组合分数排序
        merged_results = list(merged_dict.values())
        merged_results.sort(key=lambda x: x.get("combined_score", 0), reverse=True)
        
        return merged_results

    def _intersect_results(self, results1: List[Dict[str, Any]], results2: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        取两个结果列表的交集，并计算组合分数
        
        参数:
            results1: 第一个结果列表
            results2: 第二个结果列表
            
        返回:
            交集结果列表，按组合分数排序
        """
        # 如果任一列表为空，返回空列表
        if not results1 or not results2:
            return []
            
        # 创建结果字典，用于快速查找
        results1_dict = {r["video_path"]: r for r in results1}
        results2_dict = {r["video_path"]: r for r in results2}
        
        # 查找共同的视频路径
        common_paths = set(results1_dict.keys()) & set(results2_dict.keys())
        
        # 组合结果
        combined_results = []
        for path in common_paths:
            r1 = results1_dict[path]
            r2 = results2_dict[path]
            
            # 计算组合分数 (加权平均)
            r1_score = r1.get("similarity", 0)
            r2_score = r2.get("similarity", 0)
            if "description_score" in r1:
                r1_score = r1.get("description_score", 0)
            if "transcript_score" in r2:
                r2_score = r2.get("transcript_score", 0)
                
            # 使用加权平均，给描述搜索更高的权重
            combined_score = (r1_score * 0.6) + (r2_score * 0.4)
            
            # 创建组合结果
            combined_result = {
                **r1,  # 保留第一个结果的所有字段
                "transcript_score": r2_score,
                "description_score": r1_score,
                "combined_score": combined_score,
                "source": "description,transcript"  # 标记来源
            }
            combined_results.append(combined_result)
        
        # 按组合分数排序
        combined_results.sort(key=lambda x: x.get("combined_score", 0), reverse=True)
        
        return combined_results 