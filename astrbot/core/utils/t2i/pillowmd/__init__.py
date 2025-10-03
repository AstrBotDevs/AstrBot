"""
Markdown额外语法说明

<color=#FFFFFF> 以强制设定文本颜色
<color=None> 以取消强制设定文本颜色

!sgexter[对象名,参数1,参数2]绘制自定义对象（以下4个为预设对象）:
- probar 进度条 [str,float,int,str] [标签,百分比,长度,显示]
- balbar 平衡条 [str,float,int] [标签,平衡度,长度]
- chabar 条形统计图[list[[str,int],...],int,int] [对象组[[对象名,对象所占比],...],x宽度,y宽度]
- card 卡片 [str,str,int,int,str] [标题,内容,x宽度,y宽度,图片绝对文件路径]

"""
