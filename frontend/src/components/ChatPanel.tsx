import React, { useState, useRef, useEffect } from 'react';
import { Input, Button, Card, Space, Typography, Spin, Tag, message } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined } from '@ant-design/icons';
import { chatQuery, ChatResponse, ChatMessage } from '../services/api';

const { Text, Paragraph } = Typography;

interface DisplayMessage {
  role: 'user' | 'assistant';
  content: string;
  videos?: ChatResponse['videos'];
}

const ChatPanel: React.FC = () => {
  const [messages, setMessages] = useState<DisplayMessage[]>([
    {
      role: 'assistant',
      content: '你好！我是 Tesla Vision 智能助手，可以帮你搜索和分析自动驾驶视频数据。\n\n例如：\n- "帮我找傍晚下雨天，十字路口有行人的视频"\n- "统计今天的检测目标分布"',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput('');

    // 添加用户消息
    const userMsg: DisplayMessage = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);

    // 更新对话历史
    const newHistory: ChatMessage[] = [
      ...history,
      { role: 'user', content: text },
    ];

    setLoading(true);
    try {
      const response = await chatQuery(text, history);

      const assistantMsg: DisplayMessage = {
        role: 'assistant',
        content: response.reply,
        videos: response.videos,
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setHistory([
        ...newHistory,
        { role: 'assistant', content: response.reply },
      ]);
    } catch (error: any) {
      const isTimeout = error?.code === 'ECONNABORTED';
      message.error(
        isTimeout
          ? '请求超时（模型在 CPU 上推理较慢），请稍后重试'
          : '对话请求失败，请检查后端服务是否正常运行',
      );
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: isTimeout
            ? '抱歉，请求超时了。模型推理较慢，请稍后再试。'
            : '抱歉，请求失败了。请检查后端服务。',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 消息列表 */}
      <div
        style={{
          flex: 1,
          overflow: 'auto',
          padding: '16px 24px',
        }}
      >
        {messages.map((msg, idx) => (
          <div
            key={idx}
            style={{
              display: 'flex',
              marginBottom: 16,
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
            <Card
              size="small"
              style={{
                maxWidth: '75%',
                background: msg.role === 'user' ? '#e6f7ff' : '#fff',
                borderColor: msg.role === 'user' ? '#91d5ff' : '#d9d9d9',
              }}
              title={
                <Space>
                  {msg.role === 'assistant' ? (
                    <RobotOutlined style={{ color: '#1890ff' }} />
                  ) : (
                    <UserOutlined style={{ color: '#52c41a' }} />
                  )}
                  <Text strong>
                    {msg.role === 'assistant' ? 'Vision AI' : 'You'}
                  </Text>
                </Space>
              }
            >
              <Paragraph
                style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}
              >
                {msg.content}
              </Paragraph>

              {/* 检索结果：目标/场景分布统计 */}
              {msg.videos && msg.videos.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  {msg.videos.map((result, idx) => (
                    <div
                      key={idx}
                      style={{ marginBottom: idx < msg.videos!.length - 1 ? 12 : 0 }}
                    >
                      {result.object_distribution &&
                        Object.keys(result.object_distribution).length > 0 && (
                          <>
                            <Text type="secondary">检测目标分布：</Text>
                            <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                              {Object.entries(result.object_distribution).map(([name, count]) => (
                                <Tag key={name} color="green" style={{ margin: 0 }}>
                                  {name} ×{count}
                                </Tag>
                              ))}
                            </div>
                          </>
                        )}
                      {result.tag_distribution &&
                        Object.keys(result.tag_distribution).length > 0 && (
                          <>
                            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                              场景标签分布：
                            </Text>
                            <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                              {Object.entries(result.tag_distribution).map(([name, count]) => (
                                <Tag key={name} color="blue" style={{ margin: 0 }}>
                                  {name} ×{count}
                                </Tag>
                              ))}
                            </div>
                          </>
                        )}
                      {result.matched_videos && result.matched_videos.length > 0 && (
                        <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                          匹配 {result.matched_frames} 帧 / {result.matched_videos.length} 个视频
                        </Text>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        ))}

        {loading && (
          <div style={{ textAlign: 'center', padding: 8 }}>
            <Spin tip="思考中..." />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 输入框 */}
      <div
        style={{
          padding: '12px 24px',
          borderTop: '1px solid #f0f0f0',
          background: '#fff',
        }}
      >
        <Space.Compact style={{ width: '100%' }}>
          <Input.TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的问题，例如：帮我找雨天十字路口有行人的视频"
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={loading}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={loading}
            style={{ height: 'auto' }}
          >
            发送
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
};

export default ChatPanel;
