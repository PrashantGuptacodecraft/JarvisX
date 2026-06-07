"""
brain/agents/swarm.py
Implements a Multi-Agent Swarm where specialized Universal Agents collaborate.
"""
from brain.agents.universal_agent import UniversalAgent
from config.logger import get_logger

log = get_logger("agents.swarm")

class SwarmManager:
    def __init__(self, ai, brain):
        self.ai = ai
        self.brain = brain
        self.agents = {}

    def get_agent(self, role: str) -> UniversalAgent:
        if role not in self.agents:
            agent = UniversalAgent(self.ai, self.brain)
            # Customizing the system instruction based on role
            base_instruction = agent.get_tool_declarations() # To init
            
            if role == "Researcher":
                custom = "You are the Researcher Agent. Focus on using browser tools to gather data and memory tools to index knowledge. Be thorough."
            elif role == "Coder":
                custom = "You are the Coder Agent. Focus on writing and debugging python scripts using python_execute. Build robust, self-healing code."
            elif role == "Reviewer":
                custom = "You are the QA Reviewer Agent. Verify that the task is fully complete. Test endpoints or logic."
            else:
                custom = "You are an autonomous sub-agent."
                
            # We monkey-patch the run method's instruction inside UniversalAgent or 
            # we just pass the custom prefix as part of the task prompt to the agent.
            # To keep it simple, we wrap the prompt.
            agent.role_prompt = custom
            self.agents[role] = agent
        return self.agents[role]

    def run_swarm(self, task: str) -> str:
        """Decompose a massive task and pass to the swarm."""
        log.info(f"Initiating Swarm for task: {task}")
        
        # 1. Ask AI to break it down
        decomposition_prompt = f"Break this massive goal into 3 sub-tasks: 1 for a Researcher, 1 for a Coder, and 1 for a Reviewer.\nGoal: {task}"
        plan = self.ai.chat(decomposition_prompt)
        
        # 2. Run Researcher
        researcher = self.get_agent("Researcher")
        research_result = researcher.run(f"System Role: {researcher.role_prompt}\nYour Plan: {plan}\nDo the research phase now.")
        
        # 3. Run Coder
        coder = self.get_agent("Coder")
        code_result = coder.run(f"System Role: {coder.role_prompt}\nYour Plan: {plan}\nResearch context: {research_result}\nDo the coding phase now.")
        
        # 4. Run Reviewer
        reviewer = self.get_agent("Reviewer")
        final_result = reviewer.run(f"System Role: {reviewer.role_prompt}\nOriginal Goal: {task}\nCode Output: {code_result}\nDo the final review and fix issues.")
        
        return f"--- SWARM EXECUTION COMPLETE ---\n{final_result}"
