#!/usr/bin/env node
/**
 * 写作系统监控启动器
 * 
 * 在写作系统执行前启动实时监控，自动发送状态更新
 * 
 * 迁移自 ClawdBot → OpenClaw (tech-updates-writer Skill)
 * 路径已适配为相对路径 + 环境变量
 */
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const WRITER_BASE_DIR = process.env.WRITER_BASE_DIR || path.resolve(__dirname, '..');
const ALERT_CHECK_INTERVAL = 60 * 1000; // 每分钟检查一次告警

class MonitorLauncher {
  constructor(date) {
    this.date = date;
    this.supervisorProcess = null;
    this.alertCheckTimer = null;
  }

  startRealtimeSupervisor() {
    console.log('🚀 启动实时监控虾...\n');
    const scriptPath = path.join(__dirname, 'realtime-supervisor.js');
    this.supervisorProcess = spawn('node', [scriptPath, this.date], {
      stdio: ['ignore', 'pipe', 'pipe'],
      detached: false,
      env: { ...process.env, WRITER_BASE_DIR }
    });
    this.supervisorProcess.stdout.on('data', (data) => console.log(data.toString()));
    this.supervisorProcess.stderr.on('data', (data) => console.error(data.toString()));
    this.supervisorProcess.on('exit', (code) => {
      console.log(`\n监控进程退出，代码: ${code}`);
      if (this.alertCheckTimer) clearInterval(this.alertCheckTimer);
    });
    console.log(`监控进程已启动 (PID: ${this.supervisorProcess.pid})\n`);
  }

  async checkAndSendAlerts() {
    if (!fs.existsSync(WRITER_BASE_DIR)) return;
    const alertFiles = fs.readdirSync(WRITER_BASE_DIR)
      .filter(f => f.startsWith(`alert-${this.date}`) && f.endsWith('.json'))
      .map(f => path.join(WRITER_BASE_DIR, f));
    
    for (const alertFile of alertFiles) {
      try {
        const alert = JSON.parse(fs.readFileSync(alertFile, 'utf-8'));
        console.log('\n' + '='.repeat(60));
        console.log('🚨 告警内容:');
        console.log(alert.message);
        console.log('='.repeat(60) + '\n');
        const notifyFile = path.join(WRITER_BASE_DIR, `notify-${Date.now()}.txt`);
        fs.writeFileSync(notifyFile, `🚨 **写作系统告警**\n\n${alert.message}`);
        fs.unlinkSync(alertFile);
        console.log(`✅ 已发送告警: ${path.basename(alertFile)}`);
      } catch (error) { console.error(`❌ 处理告警失败: ${error.message}`); }
    }
  }

  async checkAndSendStatusUpdates() {
    if (!fs.existsSync(WRITER_BASE_DIR)) return;
    const snapshotFiles = fs.readdirSync(WRITER_BASE_DIR)
      .filter(f => f.startsWith(`status-snapshot-${this.date}`) && f.endsWith('.json'))
      .sort().slice(-1);
    if (snapshotFiles.length === 0) return;

    const latestSnapshot = path.join(WRITER_BASE_DIR, snapshotFiles[0]);
    const status = JSON.parse(fs.readFileSync(latestSnapshot, 'utf-8'));
    const lastSentFile = path.join(WRITER_BASE_DIR, '.last-sent-snapshot');
    let lastSentTime = 0;
    if (fs.existsSync(lastSentFile)) lastSentTime = parseInt(fs.readFileSync(lastSentFile, 'utf-8'));
    const currentTime = new Date(status.timestamp).getTime();
    if (currentTime > lastSentTime) {
      const msg = this.formatStatusMessage(status);
      console.log('\n' + '-'.repeat(60));
      console.log('状态更新:', msg);
      console.log('-'.repeat(60) + '\n');
      const notifyFile = path.join(WRITER_BASE_DIR, `status-update-${Date.now()}.txt`);
      fs.writeFileSync(notifyFile, msg);
      fs.writeFileSync(lastSentFile, currentTime.toString());
    }
  }

  formatStatusMessage(status) {
    let msg = `📊 **写作系统进度更新**\n\n`;
    msg += `⏰ 时间: ${new Date(status.timestamp).toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai'})}\n`;
    msg += `⏱️ 已运行: ${status.elapsed}\n📍 当前: ${status.currentPhase}\n📈 进度: ${status.progress}\n⏳ 预计剩余: ${status.estimatedCompletion}\n\n`;
    if (status.completedPhases.length > 0) msg += `✅ 已完成: ${status.completedPhases.join(', ')}\n\n`;
    if (status.issues.length > 0) {
      msg += `⚠️ 发现问题:\n`;
      status.issues.forEach((issue, idx) => { msg += `  ${idx + 1}. [${issue.severity}] ${issue.phase}: ${issue.message}\n`; });
    } else { msg += `✅ 暂无问题\n`; }
    return msg;
  }

  startAlertChecker() {
    console.log('🔔 启动告警检查器...\n');
    this.alertCheckTimer = setInterval(async () => {
      await this.checkAndSendAlerts();
      await this.checkAndSendStatusUpdates();
    }, ALERT_CHECK_INTERVAL);
  }

  async start() {
    console.log(`\n${'='.repeat(60)}`);
    console.log(`写作系统监控启动器`);
    console.log(`日期: ${this.date}`);
    console.log(`基础目录: ${WRITER_BASE_DIR}`);
    console.log(`${'='.repeat(60)}\n`);
    this.startRealtimeSupervisor();
    this.startAlertChecker();
    return new Promise((resolve) => {
      this.supervisorProcess.on('exit', (code) => {
        if (this.alertCheckTimer) clearInterval(this.alertCheckTimer);
        resolve(code);
      });
    });
  }

  stop() {
    console.log('\n🛑 停止监控...');
    if (this.supervisorProcess) this.supervisorProcess.kill();
    if (this.alertCheckTimer) clearInterval(this.alertCheckTimer);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const date = args.find(a => a.match(/^\d{4}-\d{2}-\d{2}$/)) || new Date().toISOString().split('T')[0];
  const launcher = new MonitorLauncher(date);
  process.on('SIGINT', () => { launcher.stop(); process.exit(0); });
  process.on('SIGTERM', () => { launcher.stop(); process.exit(0); });
  launcher.start().then(code => { console.log('\n✅ 监控完成'); process.exit(code); })
    .catch(error => { console.error('❌ 监控启动失败:', error); process.exit(1); });
}

export default MonitorLauncher;
