1：	打开samples文件夹编辑phase.txt和task.txt, 每个阶段一行，其中task中的--表示分割线。

2：	点击vidPlayer_working.exe 进行视频编辑，鼠标点击视频可以进行暂停和播放，空格键也能进行暂停和播放。
	视频可以选择倍速，可以拖动滑动条，可以点击界面下方左右按钮进行按帧微调，也可以使用键盘上的<- 和 -> 进行微调。
	标记完数据一定要点击save all保存，不然标记不会保存。

3：	最终结果保存再outputs文件夹中，每个视频一个文件夹

4：如果想要对于一个阶段进行多次标注，每次save之后，继续实用start ending 按钮然后再次进行保存

5：评分系统设置，samples文件夹下编辑assessment.txt，按照name#score 格式，score表示有多少个得分分级。如果score为0则为预警帧保存模式