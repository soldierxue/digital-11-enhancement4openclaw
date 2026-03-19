#!/usr/bin/env node
/**
 * 虾群写作系统 - 监工虾
 * 
 * 职责：
 * 1. 实时监控Phase 1-7执行质量
 * 2. 主动发现问题（换话题、时效性评分错误等）
 * 3. 生成详细的执行质量报告
 * 4. 发现严重问题立即告警
 * 
 * 迁移自 ClawdBot → OpenClaw (tech-updates-writer Skill)
 * 路径已适配为相对路径 + 环境变量
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 基础目录：优先使用环境变量，否则使用 Skill 根目录（scripts/ 的上一级）
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

class WritingSystemSupervisor {
  constructor(date) {
    this.date = date;
    this.baseDir = WRITER_BASE_DIR;
    this.issues = [];
    this.fixes = [];
    this.stats = {
      phase1: {},
      phase2: {},
      phase3: {},
      phase4: {},
      phase5: {},
      phase6: {},
      phase7: {}
    };
  }

  // Phase 1检查：编辑虾选题
  async checkPhase1() {
    console.log('📝 检查 Phase 1: 编辑虾选题...');
    
    const selectionFile = path.join(
      this.baseDir,
      `selection/${this.date}/${this.date}-selection.md`
    );

    if (!fs.existsSync(selectionFile)) {
      this.addIssue('P0', 'Phase 1', '选题文件不存在', selectionFile);
      return false;
    }

    const content = fs.readFileSync(selectionFile, 'utf-8');
    
    // 1. 检查话题数量
    const topicMatches = content.match(/### 话题\d+:/g);
    const topicCount = topicMatches?.length || 0;
    this.stats.phase1.topicCount = topicCount;
    
    if (topicCount !== 21) {
      this.addIssue('P1', 'Phase 1', `话题数量错误: ${topicCount}/21`, null);
    }

    // 2. 检查素材时间标注
    const timeMatches = content.match(/素材时间.*?(\d{4})-(\d{2})/g) || [];
    this.stats.phase1.timeAnnotations = timeMatches.length;
    
    if (timeMatches.length < topicCount) {
      this.addIssue('P1', 'Phase 1', 
        `素材时间标注不完整: ${timeMatches.length}/${topicCount}`, null);
    }

    // 3. 统计各年份素材占比
    const year2026 = (content.match(/素材时间.*?2026/g) || []).length;
    const year2025 = (content.match(/素材时间.*?2025/g) || []).length;
    const year2024 = (content.match(/素材时间.*?2024/g) || []).length;
    const year2023 = (content.match(/素材时间.*?2023/g) || []).length;
    
    this.stats.phase1.materialYears = {
      2026: year2026,
      2025: year2025,
      2024: year2024,
      2023: year2023
    };

    const ratio2024 = year2024 / topicCount;
    if (ratio2024 > 0.3) {
      this.addIssue('P2', 'Phase 1', 
        `2024年素材占比${(ratio2024*100).toFixed(1)}%（建议≤30%）`, null);
    }

    if (year2023 > 0) {
      this.addIssue('P1', 'Phase 1', 
        `包含${year2023}个2023年素材话题（应直接淘汰）`, null);
    }

    // 4. 检查去重
    if (!content.includes('去重') && !content.includes('昨天')) {
      this.addIssue('P2', 'Phase 1', '未发现去重检查记录', null);
    }

    console.log(`  ✅ 话题数: ${topicCount}, 2026素材: ${year2026}, 2024素材: ${year2024}`);
    return true;
  }

  // Phase 2检查：薛以致用虾创作
  async checkPhase2() {
    console.log('📝 检查 Phase 2: 薛以致用虾创作...');
    
    const draftsDir = path.join(this.baseDir, 'documents/articles', this.date);
    if (!fs.existsSync(draftsDir)) {
      this.addIssue('P0', 'Phase 2', '文章目录不存在', null);
      return false;
    }

    const v1Files = fs.readdirSync(draftsDir)
      .filter(f => f.includes(this.date) && f.includes('-v1.md'));

    this.stats.phase2.articleCount = v1Files.length;

    if (v1Files.length !== 21) {
      this.addIssue('P1', 'Phase 2', 
        `文章数量错误: ${v1Files.length}/21`, null);
    }

    // 检查每篇文章
    let shortCount = 0;
    let longCount = 0;
    
    for (const file of v1Files) {
      const content = fs.readFileSync(path.join(draftsDir, file), 'utf-8');
      const wordCount = content.length;
      
      if (wordCount < 2500) {
        shortCount++;
        this.addIssue('P2', 'Phase 2', 
          `${file} 字数偏少: ${wordCount}字`, file);
      } else if (wordCount > 4000) {
        longCount++;
        this.addIssue('P2', 'Phase 2', 
          `${file} 字数过多: ${wordCount}字`, file);
      }
    }

    this.stats.phase2.shortArticles = shortCount;
    this.stats.phase2.longArticles = longCount;

    console.log(`  ✅ 文章数: ${v1Files.length}, 字数异常: ${shortCount + longCount}`);
    return true;
  }

  // Phase 3检查：编辑虾评审
  async checkPhase3() {
    console.log('📝 检查 Phase 3: 编辑虾评审...');
    
    const reviewsDir = path.join(this.baseDir, 'reviews');
    if (!fs.existsSync(reviewsDir)) {
      this.addIssue('P2', 'Phase 3', 'reviews目录不存在（可能跳过Phase 3）', null);
      return true;
    }

    const reviewFiles = fs.readdirSync(reviewsDir)
      .filter(f => f.includes(this.date) && f.includes('-v1.md'));

    this.stats.phase3.reviewCount = reviewFiles.length;

    if (reviewFiles.length < 21) {
      this.addIssue('P2', 'Phase 3', 
        `评审数量不足: ${reviewFiles.length}/21`, null);
    }

    console.log(`  ✅ 评审数: ${reviewFiles.length}`);
    return true;
  }

  // Phase 4检查：薛以致用虾修正（关键：检查是否换话题）
  async checkPhase4() {
    console.log('📝 检查 Phase 4: 薛以致用虾修正...');
    
    const draftsDir = path.join(this.baseDir, 'documents/articles', this.date);
    if (!fs.existsSync(draftsDir)) return true;

    const v1Files = fs.readdirSync(draftsDir)
      .filter(f => f.includes(this.date) && f.includes('-v1.md'));

    let v2Count = 0;
    let topicChanges = [];

    for (const v1File of v1Files) {
      const v2File = v1File.replace('-v1.md', '-v2.md');
      const v2Path = path.join(draftsDir, v2File);

      if (!fs.existsSync(v2Path)) continue;
      v2Count++;

      const v1Content = fs.readFileSync(path.join(draftsDir, v1File), 'utf-8');
      const v2Content = fs.readFileSync(v2Path, 'utf-8');

      const v1Title = v1Content.match(/^#\s+(.+)/m)?.[1] || '';
      const v2Title = v2Content.match(/^#\s+(.+)/m)?.[1] || '';

      const similarity = this.calculateSimilarity(v1Title, v2Title);
      
      if (similarity < 0.5) {
        topicChanges.push({
          file: v1File.replace('-v1.md', ''),
          v1Title,
          v2Title,
          similarity: similarity.toFixed(2)
        });
        
        this.addIssue('P0', 'Phase 4', 
          `疑似换话题 (相似度${(similarity*100).toFixed(0)}%):\n    v1: ${v1Title}\n    v2: ${v2Title}`,
          v2File);
      } else if (similarity < 0.7) {
        this.addIssue('P2', 'Phase 4', 
          `标题变化较大 (相似度${(similarity*100).toFixed(0)}%):\n    v1: ${v1Title}\n    v2: ${v2Title}`,
          v2File);
      }
    }

    this.stats.phase4.v2Count = v2Count;
    this.stats.phase4.topicChanges = topicChanges.length;

    console.log(`  ✅ v2文章数: ${v2Count}, 疑似换话题: ${topicChanges.length}`);
    
    if (topicChanges.length > 0) {
      console.log(`  ❌ 发现${topicChanges.length}篇换话题！`);
    }

    return true;
  }

  // Phase 5检查：编辑虾最终选择（关键：检查时效性评分）
  async checkPhase5() {
    console.log('📝 检查 Phase 5: 编辑虾最终选择...');
    
    const files = fs.existsSync(this.baseDir) 
      ? fs.readdirSync(this.baseDir).filter(f => f.includes(`final-selection-${this.date}`) && f.endsWith('.md'))
      : [];

    if (files.length === 0) {
      this.addIssue('P0', 'Phase 5', '最终选择文件不存在', null);
      return false;
    }

    const finalFile = path.join(this.baseDir, files[0]);
    const content = fs.readFileSync(finalFile, 'utf-8');

    const selectedMatches = content.match(/最终选择.*?Topic \d+/gs) || [];
    this.stats.phase5.selectedCount = selectedMatches.length;

    if (selectedMatches.length !== 7) {
      this.addIssue('P1', 'Phase 5', 
        `选择数量错误: ${selectedMatches.length}/7`, null);
    }

    const sections = content.split(/### Pool \d+/);
    let material2024Count = 0;
    let wrongTimeliness = [];

    for (let i = 0; i < sections.length; i++) {
      const section = sections[i];
      
      if (section.includes('2024') && section.includes('素材时间')) {
        material2024Count++;
        
        const timelinessMatch = section.match(/时效性.*?(⭐+)/);
        if (timelinessMatch && timelinessMatch[1].length >= 4) {
          wrongTimeliness.push({
            pool: i,
            stars: timelinessMatch[1].length,
            section: section.substring(0, 200)
          });
          
          this.addIssue('P0', 'Phase 5', 
            `Pool ${i} 2024年素材给了${timelinessMatch[1].length}星（应该只有1星）`,
            null);
        }
        
        const scoreMatch = section.match(/评分.*?(\d+)\/100/);
        if (scoreMatch && parseInt(scoreMatch[1]) > 70) {
          this.addIssue('P1', 'Phase 5', 
            `Pool ${i} 2024年素材总分${scoreMatch[1]}>70（应该≤70）`,
            null);
        }
      }
    }

    this.stats.phase5.material2024 = material2024Count;
    this.stats.phase5.wrongTimeliness = wrongTimeliness.length;

    console.log(`  ✅ 选出文章数: ${selectedMatches.length}, 2024素材: ${material2024Count}`);
    
    if (wrongTimeliness.length > 0) {
      console.log(`  ❌ 发现${wrongTimeliness.length}篇2024素材评分错误！`);
    }

    return true;
  }

  // Phase 6检查：发布虾评估
  async checkPhase6() {
    console.log('📝 检查 Phase 6: 发布虾评估...');
    
    const pubFiles = fs.existsSync(this.baseDir)
      ? fs.readdirSync(this.baseDir).filter(f => f.includes(`publication-decision-${this.date}`) && f.endsWith('.md'))
      : [];

    if (pubFiles.length === 0) {
      this.addIssue('P2', 'Phase 6', '发布决策文件不存在', null);
      return true;
    }

    console.log(`  ✅ 发布决策文件存在`);
    return true;
  }

  // Phase 7检查：发布到GitHub
  async checkPhase7() {
    console.log('📝 检查 Phase 7: 发布到GitHub...');
    
    if (!fs.existsSync(PUBLISH_DIR)) {
      this.addIssue('P1', 'Phase 7', `GitHub仓库目录不存在: ${PUBLISH_DIR}`, null);
      return false;
    }

    const files = fs.readdirSync(PUBLISH_DIR)
      .filter(f => f.startsWith(this.date));

    this.stats.phase7.publishedCount = files.length;

    if (files.length < 3) {
      this.addIssue('P1', 'Phase 7', 
        `发布数量不足: ${files.length}<3`, null);
    }

    let missingFrontMatter = 0;
    
    for (const file of files) {
      const filePath = path.join(PUBLISH_DIR, file);
      const content = fs.readFileSync(filePath, 'utf-8');
      
      if (!content.startsWith('---')) {
        missingFrontMatter++;
        this.addIssue('P1', 'Phase 7', `${file} 缺少Front Matter`, file);
        continue;
      }
      
      const requiredFields = ['layout', 'title', 'date', 'categories', 'tags', 'description'];
      for (const field of requiredFields) {
        if (!content.includes(`${field}:`)) {
          this.addIssue('P2', 'Phase 7', `${file} 缺少${field}字段`, file);
        }
      }
    }

    this.stats.phase7.missingFrontMatter = missingFrontMatter;

    console.log(`  ✅ 发布文章数: ${files.length}, Front Matter异常: ${missingFrontMatter}`);
    return true;
  }

  // 工具方法：计算相似度
  calculateSimilarity(str1, str2) {
    if (!str1 || !str2) return 0;
    const set1 = new Set(str1.split(''));
    const set2 = new Set(str2.split(''));
    const intersection = new Set([...set1].filter(x => set2.has(x)));
    const union = new Set([...set1, ...set2]);
    return intersection.size / union.size;
  }

  addIssue(priority, phase, description, file = null) {
    this.issues.push({ priority, phase, description, file, timestamp: new Date().toISOString() });
  }

  generateMarkdownReport() {
    const p0Count = this.issues.filter(i => i.priority === 'P0').length;
    const p1Count = this.issues.filter(i => i.priority === 'P1').length;
    const p2Count = this.issues.filter(i => i.priority === 'P2').length;
    const status = p0Count > 0 ? '❌ 有严重问题' : p1Count > 0 ? '⚠️ 有警告' : '✅ 通过';

    let md = `# ${this.date} 写作系统执行质量报告\n\n`;
    md += `**监工虾检查时间**: ${new Date().toISOString()}\n`;
    md += `**总体状态**: ${status}\n`;
    md += `**基础目录**: ${this.baseDir}\n\n---\n\n`;

    md += `## 📊 执行概览\n\n| 指标 | 数值 |\n|------|------|\n`;
    md += `| 总问题数 | ${this.issues.length} |\n| P0严重问题 | ${p0Count} |\n| P1重要问题 | ${p1Count} |\n| P2警告 | ${p2Count} |\n\n`;

    md += `## 📋 各Phase统计\n\n`;
    md += `### Phase 1: 编辑虾选题\n- 话题数: ${this.stats.phase1.topicCount || 0}\n`;
    if (this.stats.phase1.materialYears) {
      md += `- 素材年份: 2026=${this.stats.phase1.materialYears[2026]||0}, 2025=${this.stats.phase1.materialYears[2025]||0}, 2024=${this.stats.phase1.materialYears[2024]||0}, 2023=${this.stats.phase1.materialYears[2023]||0}\n`;
    }
    md += `\n### Phase 2: 薛以致用虾创作\n- 文章数: ${this.stats.phase2.articleCount || 0}\n- 字数异常: 偏少${this.stats.phase2.shortArticles||0}篇, 偏多${this.stats.phase2.longArticles||0}篇\n`;
    md += `\n### Phase 4: 薛以致用虾修正\n- v2文章数: ${this.stats.phase4.v2Count || 0}\n- 疑似换话题: ${this.stats.phase4.topicChanges || 0}篇 ${(this.stats.phase4.topicChanges||0) > 0 ? '❌' : '✅'}\n`;
    md += `\n### Phase 5: 编辑虾最终选择\n- 选出文章数: ${this.stats.phase5.selectedCount || 0}/7\n- 2024年素材: ${this.stats.phase5.material2024 || 0}篇\n- 时效性评分错误: ${this.stats.phase5.wrongTimeliness || 0}篇 ${(this.stats.phase5.wrongTimeliness||0) > 0 ? '❌' : '✅'}\n`;
    md += `\n### Phase 7: 发布到GitHub\n- 发布文章数: ${this.stats.phase7.publishedCount || 0}\n- Front Matter异常: ${this.stats.phase7.missingFrontMatter || 0}篇\n\n`;

    if (this.issues.length > 0) {
      md += `## ⚠️ 发现的问题\n\n`;
      for (const level of ['P0', 'P1', 'P2']) {
        const items = this.issues.filter(i => i.priority === level);
        if (items.length === 0) continue;
        const labels = { P0: '严重问题（阻止发布）', P1: '重要问题（需要修复）', P2: '警告（可接受但需关注）' };
        md += `### ${level} - ${labels[level]}\n\n`;
        items.forEach((issue, idx) => {
          md += `${idx + 1}. **${issue.phase}**: ${issue.description}\n`;
          if (issue.file) md += `   - 文件: \`${issue.file}\`\n`;
          md += `\n`;
        });
      }
    } else {
      md += `## ✅ 未发现问题\n\n所有Phase执行正常，符合质量标准。\n\n`;
    }

    md += `---\n\n**报告生成**: ${new Date().toISOString()}\n**监工虾**: TechMolty 🦞\n`;
    return md;
  }

  generateJSONReport() {
    return {
      date: this.date,
      timestamp: new Date().toISOString(),
      baseDir: this.baseDir,
      summary: {
        totalIssues: this.issues.length,
        p0Issues: this.issues.filter(i => i.priority === 'P0').length,
        p1Issues: this.issues.filter(i => i.priority === 'P1').length,
        p2Issues: this.issues.filter(i => i.priority === 'P2').length,
        status: this.issues.filter(i => i.priority === 'P0').length > 0 ? 'failed' : 
                this.issues.filter(i => i.priority === 'P1').length > 0 ? 'warning' : 'passed'
      },
      stats: this.stats,
      issues: this.issues,
      fixes: this.fixes
    };
  }

  async run(phases = ['all']) {
    console.log(`\n🔍 监工虾开始检查: ${this.date}`);
    console.log(`📂 基础目录: ${this.baseDir}`);
    console.log(`📂 发布目录: ${PUBLISH_DIR}\n`);
    console.log(`=`.repeat(50));

    const phasesToRun = phases.includes('all') 
      ? ['1', '2', '3', '4', '5', '6', '7']
      : phases;

    for (const phase of phasesToRun) {
      try {
        switch(phase) {
          case '1': await this.checkPhase1(); break;
          case '2': await this.checkPhase2(); break;
          case '3': await this.checkPhase3(); break;
          case '4': await this.checkPhase4(); break;
          case '5': await this.checkPhase5(); break;
          case '6': await this.checkPhase6(); break;
          case '7': await this.checkPhase7(); break;
        }
      } catch (error) {
        console.error(`  ❌ Phase ${phase} 检查出错: ${error.message}`);
        this.addIssue('P0', `Phase ${phase}`, `检查异常: ${error.message}`, null);
      }
    }

    console.log(`=`.repeat(50));

    const jsonReport = this.generateJSONReport();
    const mdReport = this.generateMarkdownReport();
    
    const jsonFile = path.join(this.baseDir, `supervisor-report-${this.date}.json`);
    const mdFile = path.join(this.baseDir, `supervisor-report-${this.date}.md`);
    
    fs.writeFileSync(jsonFile, JSON.stringify(jsonReport, null, 2));
    fs.writeFileSync(mdFile, mdReport);

    console.log(`\n📊 检查完成\n`);
    console.log(`总问题数: ${jsonReport.summary.totalIssues}`);
    console.log(`  P0（严重）: ${jsonReport.summary.p0Issues}`);
    console.log(`  P1（重要）: ${jsonReport.summary.p1Issues}`);
    console.log(`  P2（警告）: ${jsonReport.summary.p2Issues}`);
    console.log(`\n状态: ${jsonReport.summary.status === 'passed' ? '✅ 通过' : 
                           jsonReport.summary.status === 'warning' ? '⚠️ 有警告' : '❌ 失败'}`);
    console.log(`\n报告已保存:`);
    console.log(`  - JSON: ${jsonFile}`);
    console.log(`  - Markdown: ${mdFile}\n`);

    return jsonReport.summary.p0Issues === 0;
  }
}

// CLI入口
if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const dateArg = args.find(a => a.match(/^\d{4}-\d{2}-\d{2}$/));
  const date = dateArg || new Date().toISOString().split('T')[0];
  const phasesArg = args.find(a => a.startsWith('--phases='));
  const phases = phasesArg ? phasesArg.replace('--phases=', '').split(',') : ['all'];
  
  const supervisor = new WritingSystemSupervisor(date);
  const success = await supervisor.run(phases);
  process.exit(success ? 0 : 1);
}

export default WritingSystemSupervisor;
