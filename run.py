import os
import uuid
from hospital_support_graph import hospital_support_graph

def _print_event(event: dict, _printed: set, max_length=1500):
    """打印事件内容"""
    current_state = event.get("dialog_state")
    if current_state:
        print("当前状态: ", current_state[-1])
    
    message = event.get("messages")
    if message:
        if isinstance(message, list):
            message = message[-1]
        if hasattr(message, 'id') and message.id not in _printed:
            msg_repr = str(message.content if hasattr(message, 'content') else message)
            if len(msg_repr) > max_length:
                msg_repr = msg_repr[:max_length] + " ... (已截断)"
            print(msg_repr)
            if hasattr(message, 'id'):
                _printed.add(message.id)

def main():
    # 生成会话ID
    thread_id = str(uuid.uuid4())
    patient_id = str(uuid.uuid4())

    # 配置
    config = {
        "configurable": {
            "patient_id": patient_id,
            "thread_id": thread_id,
        }
    }

    # 初始化已打印消息集合
    _printed = set()

    print("\n=== 医院智能助手测试系统 ===")
    print(f"患者ID: {patient_id}")
    print(f"会话ID: {thread_id}")
    print("输入 'quit' 或 'exit' 退出对话")
    print("=" * 40 + "\n")

    while True:
        try:
            # 获取用户输入
            question = input("\n您: ").strip()
            
            # 检查退出命令
            if question.lower() in ['quit', 'exit']:
                print("\n感谢使用医院智能助手系统，再见！")
                break
            
            # 检查输入是否为空
            if not question:
                print("请输入您的问题...")
                continue

            # 运行对话图并获取响应
            events = hospital_support_graph.stream(
                {"messages": ("user", question)}, 
                config, 
                stream_mode="values"
            )

            # 打印响应
            for event in events:
                _print_event(event, _printed)

            # 获取状态快照
            snapshot = hospital_support_graph.get_state(config)
            
            # 处理中断（如需要用户确认的操作）
            while snapshot.next:
                try:
                    user_input = input(
                        "\n是否允许执行上述操作？输入 'y' 确认，否则请说明原因：\n"
                    ).strip()
                except:
                    user_input = "y"

                if user_input.lower() == "y":
                    # 继续执行
                    result = hospital_support_graph.invoke(
                        None,
                        config,
                    )
                else:
                    # 处理用户反馈
                    result = hospital_support_graph.invoke(
                        {
                            "messages": [
                                {
                                    "role": "user",
                                    "content": f"操作被拒绝。原因: '{user_input}'. 请继续协助用户，考虑其反馈。"
                                }
                            ]
                        },
                        config,
                    )
                
                # 打印结果
                if result:
                    _print_event(result, _printed)
                
                # 更新状态快照
                snapshot = hospital_support_graph.get_state(config)

        except KeyboardInterrupt:
            print("\n\n程序被用户中断。感谢使用！")
            break
        except Exception as e:
            print(f"\n发生错误: {str(e)}")
            print("请重试...")

if __name__ == "__main__":
    main()
