#!/usr/bin/env node
/**
 * 监控通知助手
 * 
 * 读取监控脚本生成的通知文件，发送到消息通道
 * 
 * 迁移自 ClawdBot → OpenClaw (tech-updates-writer Skill)
 * 路径已适配为相对路径 + 环境变量
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const WRITER_BASE_DIR = process.env.WRITER_BASE_DIR || path.resolve(__dirname, '..');

class NotificationHelper {
  constructor() {
    this.sentNotifications = new Set();
    this.loadSentHistory();
  }

  loadSentHistory() {
    const historyFile = path.join(WRITER_BASE_DIR, '.sent-notifications.json');
    if (fs.existsSync(historyFile)) {
      const history = JSON.parse(fs.readFileSync(historyFile, 'utf-8'));
      this.sentNotifications = new Set(history);
    }
  }

  saveSentHistory() {
    const historyFile = path.join(WRITER_BASE_DIR, '.sent-notifications.json');
    fs.writeFileSync(historyFile, JSON.stringify([...this.sentNotifications], null, 2));
  }

  async checkAndSend() {
    await this.sendStatusUpdates();
    await this.sendAlerts();
  }

  async sendStatusUpdates() {
    if (!fs.existsSync(WRITER_BASE_DIR)) return;
    const files = fs.readdirSync(WRITER_BASE_DIR)
      .filter(f => f.startsWith('status-update-') && f.endsWith('.txt')).sort();
    for (const file of files) {
      if (this.sentNotifications.has(file)) continue;
      try {
        const message = fs.readFileSync(path.join(WRITER_BASE_DIR, file), 'utf-8');
        console.log(`📤 发送状态更新: ${file}`);
        console.log(message);
        console.log('---\n');
        this.sentNotifications.add(file);
        this.saveSentHistory();
      } catch (error) { console.error(`❌ 发送状态更新失败: ${error.message}`); }
    }
  }

  async sendAlerts() {
    if (!fs.existsSync(WRITER_BASE_DIR)) return;
    const files = fs.readdirSync(WRITER_BASE_DIR)
      .filter(f => f.startsWith('notify-') && f.endsWith('.txt')).sort();
    for (const file of files) {
      if (this.sentNotifications.has(file)) continue;
      try {
        const message = fs.readFileSync(path.join(WRITER_BASE_DIR, file), 'utf-8');
        console.log(`🚨 发送告警: ${file}`);
        console.log(message);
        console.log('---\n');
        this.sentNotifications.add(file);
        this.saveSentHistory();
      } catch (error) { console.error(`❌ 发送告警失败: ${error.message}`); }
    }
  }

  cleanupOldNotifications() {
    if (!fs.existsSync(WRITER_BASE_DIR)) return;
    const now = Date.now();
    const maxAge = 24 * 60 * 60 * 1000;
    const files = fs.readdirSync(WRITER_BASE_DIR)
      .filter(f => (f.startsWith('status-update-') || f.startsWith('notify-')) && f.endsWith('.txt'));
    let cleaned = 0;
    for (const file of files) {
      const filePath = path.join(WRITER_BASE_DIR, file);
      const stats = fs.statSync(filePath);
      if (now - stats.mtime.getTime() > maxAge) { fs.unlinkSync(filePath); cleaned++; }
    }
    if (cleaned > 0) console.log(`🧹 清理了${cleaned}个旧通知文件`);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const helper = new NotificationHelper();
  (async () => {
    await helper.checkAndSend();
    helper.cleanupOldNotifications();
  })().catch(error => { console.error('❌ 通知助手执行失败:', error); process.exit(1); });
}

export default NotificationHelper;
