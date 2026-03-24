from crewai import Agent, Task, Crew

# ====== 定义Agent ======

character_agent = Agent(
    role="角色设计师",
    goal="创建有深度的小说人物",
    backstory="擅长构建复杂人物关系与性格",
    verbose=True
)

plot_agent = Agent(
    role="剧情策划",
    goal="设计精彩剧情",
    backstory="擅长构建冲突与反转",
    verbose=True
)

writer_agent = Agent(
    role="小说作家",
    goal="写出高质量小说内容",
    backstory="文笔细腻，擅长情绪表达",
    verbose=True
)

# ====== 定义任务 ======

character_task = Task(
    description="设计一个玄幻男主和六位女主的人设",
    agent=character_agent
)

plot_task = Task(
    description="基于人物设定，生成故事大纲",
    agent=plot_agent
)

write_task = Task(
    description="根据大纲写第一章（2000字左右）",
    agent=writer_agent
)

# ====== 组队 ======

crew = Crew(
    agents=[character_agent, plot_agent, writer_agent],
    tasks=[character_task, plot_task, write_task],
    verbose=True
)

result = crew.kickoff()

print(result)