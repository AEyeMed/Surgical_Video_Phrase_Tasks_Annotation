工作流程：

1. [X] 1：标注phase，tasks，surgical quality，预警帧.
2. [X] 2：根据 phase、tasks、预警帧自动提取代表图像（区间中间帧、预警当前帧），并回写项目中的标注—画面关联
3. [ ] 3：图像关键帧标注组织和器械的语义分割标签
4. [ ] 4：将各个阶段标签和语义标签组合成图片描述文字。
5. [ ] 5：图文进行CLIP训练
6. [ ] 6：下游phase，tasks，预警分类，器械，组织语义分割评估
7. [ ] 7：future: 大模型进行surgical planning，根据planning进行视频帧合成
