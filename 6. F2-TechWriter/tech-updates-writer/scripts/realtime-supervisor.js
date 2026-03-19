#!/usr/bin/env node
/**
 * 实时监控虾 - Real-time Supervisor
 * 
 * 在写作系统执行期间，每10分钟检查进度并主动告知状态
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

// 发布目录：优先环境变量 → publish-config.json → 默认值
function getPublishDir() {
  if (process.env.PUBLISH_DIR) return process.env.PUBLISH_DIR;
  try {
    const config = JSON.parse(fs.readFileSync(path.join(WRITER_BASE_DIR, 'publish-config.json'), 'utf-8'));
    return path.join(config.github.localCloneDir, config.github.postsDir);
  } catch { return '/tmp/jason.xue/_posts'; }
}
const PUBLISH_DIR = getPublishDir();

class RealtimeSupervisor {
  constructor(date) {
    this.date = date;
    this.baseDir = WRITER_BASE_DIR;
    this.checkInterval = 10 * 60 * 1000; // 10分钟
    this.startTime = Date.now();
    this.lastCheck = null;
    this.currentPhase = null;
    this.statusHistory = [];
  }

  detectCurrentPhase() {
    const checks = [
      { phase: 'Phase 0', file: path.join(this.baseDir, `selection/${this.date}/topic-pool.md`), description: '话题池生成' },
      { phase: 'Phase 1', file: path.join(this.baseDir, `selection/${this.date}/${this.date}-selection.md`), description: '编辑虾选题' },
      { phase: 'Phase 2', dir: path.join(this.baseDir, `documents/articles/${this.date}`), pattern: '-v1.md', count: 21, description: '薛以致用虾创作' },
      { phase: 'Phase 3', dir: path.join(this.baseDir, 'reviews'), pattern: `${this.date}`, description: '编辑虾评审' },
      { phase: 'Phase 4', dir: path.join(this.baseDir, `documents/articles/${this.date}`), pattern: '-v2.md', description: '薛以致用虾修正' },
      { phase: 'Phase 5', file: path.join(this.baseDir, `final-selection-${this.date}.md`), description: '编辑虾最终选择' },
      { phase: 'Phase 6', file: path.join(this.baseDir, `publication-decision-${this.date}.md`), description: '发布虾评估' },
      { phase: 'Phase 7', dir: PUBLISH_DIR, pattern: this.date, description: '发布到GitHub' }
    ];

    let currentPhase = 'Not started';
    let completedPhases = [];

    for (let i = 0; i < checks.length; i++) {
      const check = checks[i];
      let exists = false;

      if (check.file) {
        exists = fs.existsSync(check.file);
      } else if (check.dir && check.pattern) {
        try {
          if (fs.existsSync(check.dir)) {
            const files = fs.readdirSync(check.dir).filter(f => f.includes(check.pattern));
            exists = check.count ? files.length >= check.count : files.length > 0;
          }
        } catch (e) { exists = false; }
      }

      if (exists) {
        completedPhases.push(check.phase);
        currentPhase = i < checks.length - 1 ? checks[i + 1].phase : 'Completed';
      } else {
        currentPhase = check.phase;
        break;
      }
    }

    return { current: currentPhase, completed: completedPhases, progress: completedPhases.length / checks.length };
  }

  async quickQualityCheck() {
    const issues = [];
    
    if (this.currentPhase?.completed?.includes('Phase 4')) {
      const draftsDir = path.join(this.baseDir, `documents/articles/${this.date}`);
      if (fs.existsSync(draftsDir)) {
        const v1Files = fs.readdirSync(draftsDir).filter(f => f.includes('-v1.md'));
        let topicChangeCount = 0;
        for (const v1File of v1Files) {
          const v2File = v1File.replace('-v1.md', '-v2.md');
          const v2Path = path.join(draftsDir, v2File);
          if (!fs.existsSync(v2Path)) continue;
          const v1Title = this.extractTitle(path.join(draftsDir, v1File));
          const v2Title = this.extractTitle(v2Path);
          if (this.calculateSimilarity(v1Title, v2Title) < 0.5) topicChangeCount++;
        }
        if (topicChangeCount > 0) {
          issues.push({ severity: 'P0', phase: 'Phase 4', message: `发现${topicChangeCount}篇疑似换话题` });
        }
      }
    }
    
    if (this.currentPhase?.completed?.includes('Phase 5')) {
      const finalFile = path.join(this.baseDir, `final-selection-${this.date}.md`);
      if (fs.existsSync(finalFile)) {
        const content = fs.readFileSync(finalFile, 'utf-8');
        if (content.includes('2024') && content.includes('⭐⭐⭐⭐⭐')) {
          issues.push({ severity: 'P0', phase: 'Phase 5', message: '可能存在2024年素材给满分的情况' });
        }
      }
    }
    
    return issues;
  }

  extractTitle(filePath) {
    try {
      const content = fs.readFileSync(filePath, 'utf-8');
      return content.match(/^#\s+(.+)/m)?.[1] || '';
    } catch (e) { return ''; }
  }

  calculateSimilarity(str1, str2) {
    if (!str1 || !str2) return 0;
    const set1 = new Set(str1.split(''));
    const set2 = new Set(str2.split(''));
    const intersection = new Set([...set1].filter(x => set2.has(x)));
    const union = new Set([...set1, ...set2]);
    return intersection.size / union.size;
  }

  estimateCompletion(phaseStatus) {
    const phaseTimes = { 'Phase 0': 5, 'Phase 1': 10, 'Phase 2': 35, 'Phase 3': 20, 'Phase 4': 25, 'Phase 5': 15, 'Phase 6': 10, 'Phase 7': 10 };
    let remainingTime = 0;
    const allPhases = Object.keys(phaseTimes);
    for (let i = phaseStatus.completed.length; i < allPhases.length; i++) {
      remainingTime += phaseTimes[allPhases[i]];
    }
    return `约${remainingTime}分钟`;
  }

  async generateStatusReport() {
    const phaseStatus = this.detectCurrentPhase();
    this.currentPhase = phaseStatus;
    const elapsed = Math.floor((Date.now() - this.startTime) / 1000 / 60);
    const issues = await this.quickQualityCheck();
    const status = {
      timestamp: new Date().toISOString(),
      elapsed: `${elapsed}分钟`,
      currentPhase: phaseStatus.current,
      completedPhases: phaseStatus.completed,
      progress: `${(phaseStatus.progress * 100).toFixed(0)}%`,
      issues,
      estimatedCompletion: this.estimateCompletion(phaseStatus)
    };
    this.statusHistory.push(status);
    return status;
  }

  formatStatusMarkdown(status) {
    let md = `## 📊 写作系统实时状态\n\n`;
    md += `**检查时间**: ${new Date(status.timestamp).toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai'})}\n`;
    md += `**已运行**: ${status.elapsed}\n**当前阶段**: ${status.currentPhase}\n**进度**: ${status.progress}\n**预计剩余**: ${status.estimatedCompletion}\n\n`;
    md += `### ✅ 已完成阶段\n`;
    if (status.completedPhases.length > 0) {
      status.completedPhases.forEach(phase => { md += `- ${phase}\n`; });
    } else { md += `暂无\n`; }
    md += `\n`;
    if (status.issues.length > 0) {
      md += `### ⚠️ 发现的问题\n`;
      status.issues.forEach((issue, idx) => { md += `${idx + 1}. **[${issue.severity}]** ${issue.phase}: ${issue.message}\n`; });
    } else { md += `### ✅ 暂无问题\n`; }
    md += `\n---\n*下次检查: 10分钟后*\n`;
    return md;
  }

  async sendStatusUpdate(status) {
    const markdown = this.formatStatusMarkdown(status);
    console.log('\n' + '='.repeat(60));
    console.log(markdown);
    console.log('='.repeat(60) + '\n');
    
    const snapshotFile = path.join(this.baseDir, `status-snapshot-${this.date}-${Date.now()}.json`);
    fs.writeFileSync(snapshotFile, JSON.stringify(status, null, 2));
    
    const p0Issues = status.issues.filter(i => i.severity === 'P0');
    if (p0Issues.length > 0) {
      console.log('🚨 发现P0问题，需要告警！');
      const alertFile = path.join(this.baseDir, `alert-${this.date}-${Date.now()}.json`);
      fs.writeFileSync(alertFile, JSON.stringify({ timestamp: status.timestamp, issues: p0Issues, message: markdown }, null, 2));
    }
    return markdown;
  }

  async start() {
    console.log(`🔍 实时监控虾启动`);
    console.log(`日期: ${this.date}`);
    console.log(`基础目录: ${this.baseDir}`);
    console.log(`检查间隔: ${this.checkInterval / 1000 / 60}分钟\n`);
    
    const initialStatus = await this.generateStatusReport();
    await this.sendStatusUpdate(initialStatus);
    
    const intervalId = setInterval(async () => {
      try {
        const status = await this.generateStatusReport();
        await this.sendStatusUpdate(status);
        if (status.currentPhase === 'Completed') {
          console.log('✅ 写作系统执行完成，停止监控');
          clearInterval(intervalId);
          await this.generateFinalReport();
          process.exit(0);
        }
      } catch (error) { console.error('❌ 监控检查出错:', error.message); }
    }, this.checkInterval);
    
    process.on('SIGINT', () => { console.log('\n🛑 收到退出信号，停止监控'); clearInterval(intervalId); process.exit(0); });
  }

  async generateFinalReport() {
    console.log('\n📊 生成最终监控报告...\n');
    const finalReport = {
      date: this.date,
      startTime: new Date(this.startTime).toISOString(),
      endTime: new Date().toISOString(),
      duration: Math.floor((Date.now() - this.startTime) / 1000 / 60),
      statusHistory: this.statusHistory,
      summary: {
        totalChecks: this.statusHistory.length,
        p0Issues: this.statusHistory.reduce((sum, s) => sum + s.issues.filter(i => i.severity === 'P0').length, 0),
        p1Issues: this.statusHistory.reduce((sum, s) => sum + s.issues.filter(i => i.severity === 'P1').length, 0)
      }
    };
    const reportFile = path.join(this.baseDir, `realtime-report-${this.date}.json`);
    fs.writeFileSync(reportFile, JSON.stringify(finalReport, null, 2));
    console.log(`最终报告已保存: ${reportFile}`);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const date = args.find(a => a.match(/^\d{4}-\d{2}-\d{2}$/)) || new Date().toISOString().split('T')[0];
  const supervisor = new RealtimeSupervisor(date);
  supervisor.start().catch(error => { console.error('❌ 实时监控启动失败:', error); process.exit(1); });
}

export default RealtimeSupervisor;
