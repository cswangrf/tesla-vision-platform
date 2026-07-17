import React, { useState } from 'react';
import { Layout, Menu, Typography } from 'antd';
import {
  DashboardOutlined,
  VideoCameraOutlined,
  RobotOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import VideoBrowser from './components/VideoBrowser';
import ChatPanel from './components/ChatPanel';

const { Header, Content, Sider } = Layout;
const { Title } = Typography;

type PageKey = 'dashboard' | 'browser' | 'chat' | 'settings';

const App: React.FC = () => {
  const [currentPage, setCurrentPage] = useState<PageKey>('browser');

  const renderContent = () => {
    switch (currentPage) {
      case 'dashboard':
        return (
          <div style={{ padding: 24 }}>
            <Title level={3}>数据看板</Title>
            <p>处理进度、标注统计等信息将在此展示。</p>
          </div>
        );
      case 'browser':
        return <VideoBrowser />;
      case 'chat':
        return <ChatPanel />;
      case 'settings':
        return (
          <div style={{ padding: 24 }}>
            <Title level={3}>设置</Title>
            <p>平台配置、模型选择等。</p>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <Layout style={{ height: '100vh' }}>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          background: '#001529',
          padding: '0 24px',
        }}
      >
        <Title level={4} style={{ color: '#fff', margin: 0 }}>
          Tesla Vision Platform
        </Title>
      </Header>
      <Layout>
        <Sider width={220} style={{ background: '#fff' }}>
          <Menu
            mode="inline"
            selectedKeys={[currentPage]}
            onClick={({ key }) => setCurrentPage(key as PageKey)}
            style={{ height: '100%', borderRight: 0 }}
            items={[
              { key: 'dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
              { key: 'browser', icon: <VideoCameraOutlined />, label: 'Video Browser' },
              { key: 'chat', icon: <RobotOutlined />, label: 'Smart Q&A' },
              { key: 'settings', icon: <SettingOutlined />, label: 'Settings' },
            ]}
          />
        </Sider>
        <Content
          style={{
            padding: 0,
            background: '#f0f2f5',
            overflow: 'auto',
          }}
        >
          {renderContent()}
        </Content>
      </Layout>
    </Layout>
  );
};

export default App;
