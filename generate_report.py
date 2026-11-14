"""Generate a Chinese analysis report from completed result tables."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import html
import os
import numpy as np
import pandas as pd
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from metacognition_analysis import LABELS,METRICS

ROOT=Path(__file__).resolve().parent
TABLE=ROOT/'outputs/tables'
REPORT=ROOT/'outputs/report'
QOUT=ROOT/'questionnaire_public/questionnaire_outputs'


def number(x,d=3):
    if pd.isna(x):return '—'
    if isinstance(x,(int,np.integer)):return str(x)
    if isinstance(x,(float,np.floating)):return f'{x:.{d}f}'
    return str(x)


def pvalue(x):
    if pd.isna(x):return '—'
    return '< .001' if x<.001 else f'{x:.3f}'


def questionnaire_findings(comparisons):
    """Summarize all four metacognitive measures in each condition-specific comparison."""
    for item,condition in [('Q13','重力'),('Q14','无重力')]:
        rows=comparisons.loc[comparisons.questionnaire_item.eq(item)].set_index('metric')
        details=[]
        for metric in ['auc','meta_d','m_ratio','auc_ratio']:
            x=rows.loc[metric]
            label='有符号 M-ratio' if metric=='m_ratio' else LABELS[metric]
            details.append(f'{label}：台球−三维差值={number(x.mean_difference_billiards_minus_3d)}，'
                           f'95% CI [{number(x.welch_ci95_low)}, {number(x.welch_ci95_high)}]，'
                           f'BH q={pvalue(x.q_bh_10_endpoints)}')
        yield f'{item}（{condition}条件）的四项元认知结果，采用本题全部10项终点BH校正：'+'；'.join(details)+'。'
        significant=rows.loc[rows.q_bh_10_endpoints.lt(.05)]
        if significant.empty:
            yield f'{item}的全部10项指标在该校正下均未达显著。'
        else:
            names='、'.join(LABELS[m] for m in significant.index)
            yield f'{item}通过本题10项BH校正的指标为{names}；其余指标未达显著。'


class Report:
    def __init__(self):
        self.md=[];self.html=[];self.doc=Document()
        sec=self.doc.sections[0];sec.page_width=Inches(8.5);sec.page_height=Inches(11)
        sec.top_margin=sec.bottom_margin=Inches(.7);sec.left_margin=sec.right_margin=Inches(.65)
        for name in ['Normal','Title','Heading 1','Heading 2','Heading 3']:
            style=self.doc.styles[name];style.font.name='Calibri'
            style._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Microsoft YaHei')
        self.doc.styles['Normal'].font.size=Pt(9)
        self.doc.styles['Normal'].paragraph_format.space_after=Pt(5)
        for name in ['Heading 1','Heading 2','Heading 3']:
            self.doc.styles[name].font.color.rgb=RGBColor.from_string('355C7D')
        self.doc.styles['Title'].font.color.rgb=RGBColor(0,0,0)

    def heading(self,text,level=1):
        self.md.append('#'*level+' '+text+'\n')
        self.html.append(f'<h{level}>{html.escape(text)}</h{level}>')
        self.doc.add_heading(text,level=0 if level==1 else min(level-1,3))

    def paragraph(self,text):
        self.md.append(text+'\n');self.html.append('<p>'+html.escape(text)+'</p>');self.doc.add_paragraph(text)

    def table(self,headers,rows):
        formatted=[[number(v) for v in row] for row in rows]
        self.md.extend(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                       ['| '+' | '.join(row)+' |' for row in formatted]+[''])
        self.html.append('<div class="table"><table><thead><tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(c)+'</td>' for c in row)+'</tr>' for row in formatted)+'</tbody></table></div>')
        table=self.doc.add_table(rows=1,cols=len(headers));table.style='Light Shading Accent 1'
        for cell,text in zip(table.rows[0].cells,headers):cell.text=text
        pr=table.rows[0]._tr.get_or_add_trPr();repeat=OxmlElement('w:tblHeader');pr.append(repeat)
        for vals in formatted:
            for cell,text in zip(table.add_row().cells,vals):cell.text=text
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for run in p.runs:run.font.size=Pt(7.3)

    def figure(self,stem,caption):
        path=ROOT/'outputs/figures'/f'{stem}.png'
        if not path.exists():raise FileNotFoundError(path)
        relative='../figures/'+path.name
        self.md.extend([f'![{caption}]({relative})','',caption,''])
        self.html.append(f'<figure><img src="{html.escape(relative)}" alt="{html.escape(caption)}"><figcaption>{html.escape(caption)}</figcaption></figure>')
        p=self.doc.add_paragraph();p.paragraph_format.keep_with_next=True
        p.add_run().add_picture(str(path),width=Inches(6.1 if stem=='Figure_4_scanpath_organization' else 7.0))
        self.doc.add_paragraph(caption)

    def save(self):
        REPORT.mkdir(parents=True,exist_ok=True)
        stem='轨迹判断与元认知分析报告'
        (REPORT/(stem+'.md')).write_text('\n'.join(self.md),encoding='utf-8')
        css='body{max-width:1120px;margin:40px auto;padding:0 30px;font:16px/1.65 "Microsoft YaHei",sans-serif;color:#24323d}h1,h2,h3{line-height:1.35}h2,h3{color:#355c7d}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:7px 9px;border-bottom:1px solid #d7dadd;text-align:left}th{background:#f5f3ef}figure{margin:30px 0}img{max-width:100%;height:auto}figcaption{font-size:14px;color:#68737b}a{color:#355c7d}'
        (REPORT/(stem+'.html')).write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>'+stem+'</title><style>'+css+'</style><body>'+'\n'.join(self.html)+'</body></html>',encoding='utf-8')
        self.doc.save(REPORT/(stem+'.docx'))

    def output_index(self,directory,label):
        self.paragraph(label+'（完整机器可读结果）：')
        files=sorted(directory.glob('*.csv'))
        self.md.append('\n'.join('- ['+p.name+']('+Path(os.path.relpath(p,REPORT)).as_posix()+')' for p in files)+'\n')
        self.html.append('<ul>'+''.join('<li><a href="'+html.escape(Path(os.path.relpath(p,REPORT)).as_posix())+'">'+html.escape(p.name)+'</a></li>' for p in files)+'</ul>')
        self.doc.add_paragraph('；'.join(p.name for p in files))


def build():
    read=lambda name:pd.read_csv(TABLE/name)
    effects=read('paired_condition_effects.csv');flow=read('metad_sample_flow.csv')
    dsm=read('dsm_results_by_metric.csv');cont=read('dsm_continuous_by_metric.csv')
    fits=read('metad_fit_status_counts.csv');sensitivity=read('metad_sensitivity.csv')
    recovery=read('metad_parameter_recovery.csv');power=read('mixed_model_power_summary.csv')
    qcomp=pd.read_csv(QOUT/'questionnaire_group_comparisons.csv')
    mod=pd.read_csv(QOUT/'questionnaire_moderation_summary.csv')
    r=Report();r.heading('轨迹判断与元认知分析报告')
    r.paragraph('生成时间 '+datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y年%m月%d日 %H:%M')+'。本报告呈现行为、元认知、眼动和问卷分析结果，各分析分别报告差值方向、样本量及区间。')
    r.paragraph('零重力条件伴随较低的一阶表现、AUC和meta-d′。M-ratio及AUC-ratio的直接条件比较未提供效率下降的明确证据。每条件36试次、稀疏信心计数及接近零的d′会影响个体效率估计，因此效率结论结合共同样本和恢复检查解释。')
    r.paragraph('AUC差异仍可反映一阶知觉证据质量的变化；这些结果不足以据此确认额外的元认知监控受损，也不构成两条件效率等效的证据。效率点估计、区间及对计数结构的敏感性需要共同报告。')
    r.heading('1 分析范围和指标',2)
    r.paragraph('主样本由behavioral_data和eye_tracking_data中的393组匹配记录构成。问卷分析使用questionnaire_public/behavioral_data中的286份行为记录，按公开P编号与questionnaire_data_public.csv一对一连接。主样本与问卷行为样本分别应用质量标准并报告分母。')
    r.paragraph('质量控制分别针对行为、信心、眼动和序列数据。SDT使用ExpectedAnswer的0/1作为真实选项类别、UserAnswer的0/1作为选择、整数1–7作为信心；逐条件构建2×2×7原始计数。等方差条件最大似然保留两种选择各自的信心阈值，meta-c=(meta-d′/d′)×c；每格加1/14，与Hautus一阶修正一致。M-ratio=meta-d′/d′，不截断负值或大于1的值。AUC-ratio=观测AUC/相同d′、判准与信心阈值下的SDT期望AUC，恒定信心时AUC按分析规则记为未定义。')
    r.paragraph('对AUC、meta-d′、有符号M-ratio和AUC-ratio分别实施配对条件比较、准确率相关、极端组SPAM/DSM、连续关联及逐人剔除分析。M-ratio与AUC-ratio属于不同构造；AUC-ratio仍可依赖一阶表现，不能视为自动完全消除难度影响。对低d′和36试次下估计精度的检查用于限定解释。')
    r.heading('2 样本和直接条件比较',2)
    r.table(['指标','信心计数QC','有重力有限n','无重力有限n','有限配对n'],[(LABELS[x.metric],x.confidence_count_qc_participants,x.finite_gravity,x.finite_zero_gravity,x.finite_paired) for x in flow.itertuples()])
    r.table(['指标','配对n','有重力M','无重力M','无−有','95% CI','dz','p','BH q'],[(LABELS[x.metric],x.n,x.gravity_mean,x.zero_gravity_mean,x.difference_zero_minus_gravity,f'[{number(x.ci95_low)}, {number(x.ci95_high)}]',x.cohens_dz,pvalue(x.paired_t_p),pvalue(x.p_bh)) for x in effects.itertuples()])
    r.paragraph('主表BH家族包含10个行为及元认知终点；机器表另提供四个元认知终点的BH q。配对t检验为双尾；Wilcoxon与各终点描述统计保留在机器表。恒定信心排除后，AUC的有限配对人数为258，不能用351名计数QC合格人数替代。')
    r.paragraph('M-ratio均值为逐人meta-d′/d′比值的算术平均，不等于两个组均值相除；不同终点使用各自可用配对样本。')
    r.figure('Figure_1_behavioral_signature','图1 行为与元认知条件比较。a为配对标准化差值及缩放后的均值差95% CI，方向为无重力减有重力。右侧第一行b、c为准确率、决策反应时中位数（ms）；第二行d、e为AUC、AUC-ratio；第三行f、g为meta-d′、M-ratio。分布面板显示小提琴分布、配对连线、个体点及均值95% CI。')
    r.heading('3 效率估计可靠性和敏感性',2)
    r.table(['条件','拟合状态','人数'],[(x.condition,x.status,x.n) for x in fits.itertuples()])
    r.table(['样本规则','指标','配对n','无−有','95% CI','p'],[(x.analysis,LABELS[x.metric],x.n,x.difference_zero_minus_gravity,f'[{number(x.ci95_low)}, {number(x.ci95_high)}]',pvalue(x.paired_t_p)) for x in sensitivity.itertuples()])
    coarse=read('metad_three_level_sensitivity.csv')
    r.table(['固定合并信心等级','指标','n','无−有','95% CI','p'],[(x.analysis,LABELS[x.metric],x.n,x.difference_zero_minus_gravity,f'[{number(x.ci95_low)}, {number(x.ci95_high)}]',pvalue(x.paired_t_p)) for x in coarse.itertuples()])
    r.paragraph('额外样本规则在两条件使用相同阈值，保留|d′|>.10以及d′>.10的结果；固定信心合并映射为1–3、4–5、6–7。以上是数值稳定性敏感性分析，未经预注册。个体MLE采用等方差条件最大似然，相关计数、拟合状态、似然和条件预测检查分别导出。参数恢复与敏感性分析评价个体估计的精度。')
    r.table(['恢复情景','指标','成功/总数','真值','估计均值','偏差','RMSE'],[(x.scenario,LABELS[x.metric],f'{x.valid_fits}/{x.replicates}',x.true_value,x.mean_estimate,x.bias,x.rmse) for x in recovery.itertuples()])
    r.paragraph('恢复模拟每情景200次、每次36试次，比较分散信心和高信心集中两种计数结构，以及d′=.8/1.2；真M-ratio=.6。失败拟合单列，偏差/RMSE条件于成功拟合。分位数表示模拟估计的抽样分布，不能作为真实样本估计的置信区间。')
    r.heading('4 两类信心模型与一阶表现',2)
    joint=read('coupling_joint_interpretation.csv')
    r.table(['模型','估计目标','OR','95% CI','p'],[(x.model,x.estimand,x.odds_ratio,f'[{number(x.ci_low)}, {number(x.ci_high)}]',pvalue(x.p_value)) for x in joint.itertuples()])
    r.paragraph('准确率逻辑模型的交互表示同一人信心每提高一级时，正确反应优势的条件间斜率比；有序信心模型的交互表示正确/错误关联的信心分离在条件间的比例优势比。两个模型的结局、链接和条件化方向不同，各自的估计、区间及p值分别陈述。二者均不直接估计已相对于一阶敏感性标准化的效率。')
    r.paragraph('有序信心主分析采用Laplace近似（每维1积分点）、累积logit链接以及被试截距与条件斜率结构。稳定对数概率实现通过独立数值梯度和正定Hessian核对；每维15点积分作为数值敏感性分析，并用21点估计核对参数精度。')
    integration=[]
    for model,term in [('confidence_clmm','conditionzero_gravity'),('confidence_bias_clmm','conditionzero_gravity:correct_f1'),('interpretation_confidence_clmm','conditionzero_gravity:interpretationbilliards')]:
        for suffix,label in [('stable_coefficients.csv','主分析 Laplace'),('agq15_sensitivity_coefficients.csv','15点积分敏感性')]:
            item=read(model+'_'+suffix)
            z=item[item.term.eq(term)].iloc[0]
            integration.append((model,label,z.odds_ratio,f'[{number(z.ci_low)}, {number(z.ci_high)}]',pvalue(z.p_value)))
    r.table(['有序模型','积分设置','目标OR','95% CI','p'],integration)
    r.paragraph('高精度积分结果与主分析一并保留，用于评价有序模型对数值近似的敏感性。解释两类信心模型时，以各自的结局、条件化方向、区间和积分设置为依据；相对于一阶敏感性的效率判断另由M-ratio等指标提供。')
    comparison=read('ordinal_optimizer_comparison.csv')
    r.table(['模型/项','初始优化输出OR','初始优化输出p','稳定似然OR','稳定似然p'],[(x.model+' / '+x.term,x.odds_ratio_initial_optimizer,pvalue(x.p_value_initial_optimizer),x.odds_ratio_stable_likelihood,pvalue(x.p_value_stable_likelihood)) for x in comparison.itertuples()])
    r.paragraph('初始有序模型优化输出存在收敛或Hessian问题。表中同时记录初始优化输出与稳定似然估计，模型解释采用通过独立梯度、正定Hessian及15点和21点积分核对的估计。两种数值实现使用相同样本、固定效应、随机截距、条件斜率和Laplace近似。两类信心模型及效率指标分别按照各自的估计目标解释。')
    r.figure('Figure_2_metacognitive_monitoring','图2 原始信心—准确率关系与六类模型估计。后两项分别标明准确率模型和有序信心模型的不同交互；误差线为95% CI。')
    primary=read('figure2_key_model_coefficients.csv')
    r.table(['模型终点','尺度','无/有比率','95% CI','p'],[(x.label.replace('\n',' '),x.effect_type,x.ratio,f'[{number(x.ci_low)}, {number(x.ci_high)}]',pvalue(x.p)) for x in primary.itertuples()])
    r.paragraph('前四项模型的条件主效应对应参考速度、尺寸配对及目标侧组合；含条件交互时，这些参考单元效应与全样本未调整配对差值具有不同估计目标。完整协变量及交互系数在behavior_mixed_model_coefficients.csv中。')
    corr=read('accuracy_metacognition_correlations.csv')
    r.table(['指标','条件','n','Pearson r','p','Spearman ρ','p'],[(LABELS[x.metric],x.condition,x.n,x.pearson_r,pvalue(x.pearson_p),x.spearman_rho,pvalue(x.spearman_p)) for x in corr.itertuples()])
    r.heading('5 眼动和探索性序列结果',2)
    eye=read('eye_coverage_threshold_sensitivity.csv')
    r.table(['覆盖阈值','n','位置区占比增加百分点','95% CI','p'],[(x.coverage_threshold,x.n,x.position_share_change_pp,f'[{number(x.ci95_low_pp)}, {number(x.ci95_high_pp)}]',pvalue(x.p)) for x in eye.itertuples()])
    r.figure('Figure_3_gaze_reallocation','图3 注视分配、各区域时长及次数。原始尺度与相应95% CI分别呈现；条件比较方向保持一致。')
    counts=dsm.groupby(['metric','representation','condition']).agg(n_significant=('permutation_p_fdr',lambda x:int((x<.05).sum())),n_low=('n_low','first'),n_high=('n_high','first')).reset_index()
    r.table(['指标','表示','条件','低/高组n','FDR显著dyad数'],[(LABELS[x.metric],x.representation,x.condition,f'{x.n_low}/{x.n_high}',x.n_significant) for x in counts.itertuples()])
    sig=read('scanpath_selected_contrasts_by_metric.csv')
    r.table(['指标','条件','转移','低/高组n','低−高百分点','95% CI','BH q'],[(LABELS[x.metric],x.condition,x.dyad,f'{x.n_low}/{x.n_high}',100*x.low_minus_high,f'[{number(100*x.ci95_low)}, {number(100*x.ci95_high)}]',pvalue(x.p_fdr)) for x in sig.itertuples()])
    r.paragraph('序列组间区间采用3500次组内参与者bootstrap，随机种子为20260716（基础种子20260713加3）。每项元认知指标独立初始化同一随机种子，选中转移按BH校正p值及转移名称排序。')
    r.paragraph('每个指标分别按本条件Q1/Q3严格低于/高于分组，并在其自身候选样本中重算M−2SD的dyad QC。BH校正在各指标、条件及event/duration表示内分别进行，每项置换5000次；另提供跨四指标校正列。不同指标的结果来自同一批原始数据，不能当作独立重复实验。')
    significant=cont[cont.p_fdr<.05]
    r.table(['指标','表示','条件','dyad','n','连续斜率','BH q'],[(LABELS[x.metric],x.representation,x.condition,x.dyad,x.n,x.metric_slope,pvalue(x.p_fdr)) for x in significant.itertuples()])
    r.paragraph('连续回归采用HC3稳健标准误。选中dyad相加得到的转移特征与指标的相关属于同数据后选择描述；完整相关、样本量及选中转移在scanpath_signature_associations_by_metric.csv中。')
    r.figure('Figure_4_scanpath_organization','图4 探索性序列结果。a、b分别为AUC与meta-d′的无重力duration转移矩阵，数值为各指标低组减高组的百分点；星号与边框表示相应家族FDR<.05。c为连续关联，紫色AUC使用上方横轴，绿色meta-d′使用下方横轴；散点与回归线描述指标和转移特征的连续关联，区间为95% CI。d为有向转移网络，第三条加粗箭头表示两指标共同通过FDR的Ball Medium→Position Long转移；框中紫色差值为AUC、绿色差值为meta-d′，单位为低组减高组的百分点。连续关联属于同数据后选择描述。')
    r.heading('6 问卷的两项主要组间比较',2)
    r.paragraph('问卷的主要比较为：按Q13回答独立划分三维重力理解组与二维台球式组，比较其在重力条件下的表现；按Q14回答重新分组，比较三维零/微重力理解组与二维台球式组在无重力条件下的表现。两项比较均包含全部10项指标，包括AUC、meta-d′、有符号M-ratio和AUC-ratio。每项比较独立应用相应条件QC，不要求另一条件合格。统计单位为参与者，使用Welch双尾t、95% CI和Hedges g；方向为二维台球式减三维理解。')
    r.table(['比较','指标','3D/台球n','3D M','台球M','台球−3D','95% CI','p','BH q'],[(x.comparison,LABELS[x.metric],f'{x.n_three_d}/{x.n_billiards}',x.mean_three_d,x.mean_billiards,x.difference_billiards_minus_three_d,f'[{number(x.ci95_low)}, {number(x.ci95_high)}]',pvalue(x.p_value),pvalue(x.p_bh)) for x in qcomp.itertuples()])
    r.paragraph('主要结论采用每个问题/条件全部10项终点的BH校正；四项元认知指标另有补充校正。问卷在任务后填写，组间差别反映探索性关联。逐终点保留过程和全体286条一对一匹配审计在questionnaire_public/questionnaire_outputs内。')
    for paragraph in questionnaire_findings(qcomp):r.paragraph(paragraph)
    r.figure('Figure_S4_questionnaire_group_comparisons','图S4 问卷选择分布及任务理解组间差别。上方a为Q14两个焦点选项：二维台球式58/262（22.1%），三维零/微重力204/262（77.9%）；b为全体286人的三维理解选择：Q13为246/286（86.0%），Q14为204/286（71.3%）。下方c、d分别为Q13有重力和Q14无重力的组间比较；点为Hedges g，误差线为Welch均值差95% CI按同一合并标准差及小样本修正缩放，方向为二维台球式减三维理解。完整组间统计与校正见表格。')
    r.heading('7 补充的条件与任务理解交互分析',2)
    r.paragraph('在上述两项条件内比较之外，另对Q14分组实施条件×理解组补充检验。准确率GLMM和有序信心CLMM包含速度、方向性尺寸配对、目标侧、线性和二次试次进程、条件与速度及尺寸交互，以及被试随机截距和条件斜率；AUC、meta-d′、有符号M-ratio和AUC-ratio比较同一参与者的无重力减重力差值，使用异方差组间检验及5000次组内参与者bootstrap。六项交互检验统一使用六终点BH校正。')
    r.table(['终点','3D/台球n','交互/差异之差','95% CI','p','六终点BH q'],[(LABELS.get(x.metric,x.metric),f'{int(x.n_three_d)}/{int(x.n_billiards)}',x.effect,f'[{number(x.ci95_low)}, {number(x.ci95_high)}]',pvalue(x.p_value),pvalue(x.p_bh_all_six)) for x in mod.itertuples()])
    r.paragraph('模型交互在OR尺度上，无参数汇总指标的交互在原始差异之差尺度上；它们的零点分别为1和0。标准化预测及其条件差异另存questionnaire_moderation_standardized_predictions/contrasts.csv，解释时不以一组显著而另一组不显著代替直接交互检验。')
    r.paragraph('Q14条件内比较中，AUC-ratio通过10终点BH校正；AUC和meta-d′仅在四元认知终点家族内通过校正。条件×理解的直接调节中，AUC和AUC-ratio的原始p值小于.05，校正后均未达到.05。准确率、信心、meta-d′及M-ratio的直接调节检验未达到.05。')
    r.heading('8 设计敏感性与复杂模型模拟功效',2)
    r.table(['情景真OR','模拟次数','可用/失败','总分母检出率','MC SE','成功拟合覆盖率','偏差','RMSE'],[(x.true_or,x.replicates,f'{x.usable}/{x.failed}',x.detection_all_replicates,x.monte_carlo_se,x.coverage_95_successful,x.bias,x.rmse) for x in power.itertuples()])
    r.paragraph('复杂模型模拟采用实际信心—准确率GLMM的试次设计、任务协变量及随机效应协方差。每次重新生成参与者随机效应和二项结局，并用同一模型公式重新拟合。条件×信心交互设为OR=1和OR=.90，各100次；其余参数根据实际拟合结果设定。非收敛、奇异及错误拟合计入总分母并单列，检出率同时给Monte Carlo误差。')
    design=read('paired_design_sensitivity.csv')
    r.table(['终点','实际有效n','80%可检出dz','dz=.10模拟检出率','dz=.20模拟检出率','dz=.30模拟检出率'],[(LABELS[m],int(g.n.iloc[0]),g.detectable_dz_80.iloc[0],g.loc[g.assumed_dz.eq(.1),'simulated_detection'].iloc[0],g.loc[g.assumed_dz.eq(.2),'simulated_detection'].iloc[0],g.loc[g.assumed_dz.eq(.3),'simulated_detection'].iloc[0]) for m,g in design.groupby('metric',sort=False)])
    r.paragraph('配对设计另以每终点实际有效n、假设dz=0/.10/.20/.30各5000次正态差值模拟，并与非中心t解析功效核对。以上评价已完成设计对假设效应的敏感性。')
    r.heading('9 稳健性结果和复现入口',2)
    r.figure('Figure_S1_task_structure_and_time_course','图S1 速度、尺寸配对和试次进程结果。模型使用实际行顺序的线性/二次项，解释范围保持一致。')
    r.figure('Figure_S2_quality_control_and_robustness','图S2 样本流、眼动覆盖、序列QC和逐人剔除。四项元认知指标的逐人剔除表位于metacognition_leave_one_subject_out.csv。')
    loo=read('metacognition_leave_one_subject_out.csv')
    r.table(['指标','n','完整差值','逐人剔除最小值','最大值','方向保持'],[(LABELS[x.metric],x.n,x.full_difference,x.loo_min,x.loo_max,'是' if x.sign_stable else '否') for x in loo.itertuples()])
    rt=read('rt_sensitivity.csv').iloc[0]
    r.paragraph(f'决策时间限制为{int(rt.lower_ms)}–{int(rt.upper_ms)} ms后，n={int(rt.n)}，配对中位数差值{number(rt.zero_minus_gravity)} ms，95% CI [{number(rt.ci95_low)}, {number(rt.ci95_high)}]，p={pvalue(rt.paired_p)}。完整任务因素、遮挡时长及眼动模型系数与诊断均保存在下列机器表中。')
    r.paragraph('完整运行命令为python run_analysis.py。已拟合的R模型可在直接核对输入表相等后用--reuse-models复用；模拟按scenario/replicate checkpoint续接。默认运行会生成全部主分析、问卷比较及调节、模拟、图片和本报告。')
    r.heading('10 方法依据和结果表目录',2)
    r.paragraph('Maniscalco & Lau (2012): https://doi.org/10.1016/j.concog.2011.09.021；Fleming (2017): https://doi.org/10.1093/nc/nix007；Rahnev (2025): https://doi.org/10.1038/s41467-025-56117-0。AUC-ratio按SDT预期AUC对观测AUC进行归一化，方法依据Rahnev（2025）。')
    for directory,label in [(TABLE,'主分析表'),(QOUT,'问卷输出')]:
        r.output_index(directory,label)
    r.save()
    print(REPORT/'轨迹判断与元认知分析报告.docx')

if __name__=='__main__':build()
