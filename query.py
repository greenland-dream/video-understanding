#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Command-line tool for video querying

Usage: 
    1. Command-line mode: python query.py "your natural language query"
    2. Debug mode: modify the DEBUG_QUERY variable below, and run python query.py

Examples:
    python query.py "Help me find videos describing the Grand Canyon, with people walking, cloudy day, people admiring the beauty"
"""

import sys
from modules.video_query import VideoQuerySystem

# Debug query string - modify this variable for debugging
# Set to None to use command-line arguments
DEBUG_QUERY = None


def main():
    """Main function, processes command-line arguments and executes video query"""
    # Determine query string
    if DEBUG_QUERY is not None:
        query = DEBUG_QUERY
        print(f"使用调试查询: \"{query}\"")
    elif len(sys.argv) > 1:
        query = sys.argv[1]
        print(f"使用命令行查询: \"{query}\"")
    else:
        print("用法: python query.py \"你的自然语言查询\"")
        print("  或: 修改 DEBUG_QUERY 变量后直接运行")
        sys.exit(1)
    
    # Initialize the system
    query_system = VideoQuerySystem(
        db_path="db/data/video_processing.db",
        chroma_path="db/data/chroma_db"
    )
    
    try:
        # Execute search
        results = query_system.search_videos(query)
        
        # Print results
        print(f"\n找到 {len(results)} 个匹配查询的视频: \"{query}\"\n")
        
        for i, result in enumerate(results[:20]):  # Show top 20
            print(f"结果 {i+1}: {result['video_path']}")
            
            # Display similarity scores based on result type
            if 'description_score' in result and result.get('description_score') is not None:
                print(f"  描述相似度: {result['description_score']:.4f}")
            
            if 'transcript_score' in result and result.get('transcript_score') is not None:
                print(f"  对话相似度: {result['transcript_score']:.4f}")
            
            if 'combined_score' in result and result.get('combined_score') is not None:
                print(f"  综合相似度: {result['combined_score']:.4f}")
            
            # Print video description
            if 'description' in result:
                print(f"  描述: {result['description']}")
            elif 'document' in result:
                print(f"  描述: {result['document']}")
            
            # Print dialogue content (if available)
            if 'transcript' in result and result['transcript']:
                print(f"  对话: {result['transcript']}")
            
            # Print some metadata fields
            for key in ['拍摄场景', '人物', '拍摄时间', '拍摄主地点']:
                if key in result['metadata'] and result['metadata'][key]:
                    print(f"  {key}: {result['metadata'][key]}")
            
            print("")
    
    finally:
        # Clean up resources
        query_system.close()

if __name__ == "__main__":
    main() 