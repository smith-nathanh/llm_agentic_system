from agents.base import Agent


if __name__ == "__main__":

    agent = Agent() # defaults to embedded memory, but can be changed to 'cuda' or 'openvino' for acceleration
    agent.run()



