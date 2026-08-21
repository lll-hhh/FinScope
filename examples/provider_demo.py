"""Provider configuration demo. Credentials are read only from environment."""

from finscope import OpenAICompatibleChatModel, local_qwen_profile


model = OpenAICompatibleChatModel(local_qwen_profile())
print(model.chat([{"role": "user", "content": "只回答：连接成功"}]))
