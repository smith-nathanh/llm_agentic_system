# agents/brain/core.py
from agents.brain.utils.build_prompt import default_prompt_builder
from agents.brain.utils.examples import prompt_examples
from agents.brain.modules.simple_modules import ControlModule, MainModule, MemoryModule
import json


class Brain:
    def __init__(self, toolkit, forget_threshold: int = 10, verbose: bool = True, memory_type='embedded'):

        # Set the verbose flag
        self.verbose = verbose

        # Initialize memory based on the memory_type parameter
        if memory_type == 'cuda':
            from .memory.cuda_embedded import CudaMemoryWithEmbeddings
            self.memory = CudaMemoryWithEmbeddings(forget_threshold=forget_threshold)
        elif memory_type == 'openvino':
            from .memory.ov_embedded import OpenvinoMemoryWithEmbeddings
            self.memory = OpenvinoMemoryWithEmbeddings(forget_threshold=forget_threshold)
        elif memory_type == 'embedded':
            from .memory.embedded import EmbeddedMemory
            self.memory = EmbeddedMemory(forget_threshold=forget_threshold)
        else:
            from .memory.simple import SimpleMemory
            self.memory = SimpleMemory(forget_threshold=forget_threshold)

        self.toolkit = toolkit  # Add toolkit to Brain

        # Initialize modules using the specialized classes
        self.modules = [
            ControlModule(),
            MainModule(),
            MemoryModule(brain=self)
        ]

    def get_modules_info(self):
        """
        Dynamically generates a list of available modules and their descriptions.
        """
        module_info = {}
        for idx, module in enumerate(self.modules):
            module_info[idx] = {
                'name': module.__class__.__name__,
                'description': module.system_message  # Assuming each module has a system_message attribute
            }
        return module_info

    def get_tool_info(self):
        """
        Generates a dictionary of available tools and their descriptions.
        """
        tool_info = {tool.name: tool.description for tool in self.toolkit.tools}
        return tool_info

    def determine_action(self, user_input: str) -> dict:
        """
        Use the PreFrontalCortex to determine if the input should be handled by a tool or a module.

        Returns:
            - Dictionary containing action information.
        """
        # Get tool and module information
        tool_info = self.get_tool_info()
        module_info = self.get_modules_info()

        # Build tool descriptions
        tool_descriptions = "\n".join([f"{name}: {desc}" for name, desc in tool_info.items()])

        # Build module descriptions
        module_descriptions = "\n".join(
            [f"{idx}: {info['name']} - {info['description']}" for idx, info in module_info.items()]
        )

        # Build examples
        examples = prompt_examples

        # Construct the prompt for the PreFrontalCortex to make a decision
        prompt = default_prompt_builder(tool_descriptions=tool_descriptions, module_descriptions=module_descriptions,
                                        examples=examples, user_input=user_input)

        # The PreFrontalCortex determines which action to take
        prefrontal_cortex = self.modules[0]  # Assuming PreFrontalCortex is at index 0
        decision_response = prefrontal_cortex.process(user_input=prompt, memory=self.memory.short_term_df)

        # Parse the JSON response
        try:
            decision = json.loads(decision_response)
            use_tool = decision.get('use_tool', False)
            refined_prompt = decision.get('refined_prompt', user_input)

            if use_tool:
                tool_name = decision.get('tool_name')
                # Find the tool index based on the tool name
                tool_index = next((idx for idx, tool in enumerate(self.toolkit.tools) if tool.name == tool_name), None)
                if tool_index is not None:
                    return {
                        "use_tool": True,
                        "tool_index": tool_index,
                        "tool_name": tool_name,
                        "refined_prompt": refined_prompt
                    }
            else:
                module_index = int(decision.get('module_index', 0))
                return {
                    "use_tool": False,
                    "module_index": module_index,
                    "module_name": self.modules[module_index].__class__.__name__,
                    "refined_prompt": refined_prompt
                }
        except (json.JSONDecodeError, KeyError, ValueError):
            # If parsing fails, default to using the FrontalLobe
            return {
                "use_tool": False,
                "module_index": 1,  # FrontalLobe
                "module_name": "FrontalLobe",
                "refined_prompt": user_input
            }

    def process_input(self, user_input: str) -> str:
        """
        Process the input by deciding whether to use a tool or a module.
        """
        action = self.determine_action(user_input)
        if action["use_tool"]:
            # Use the specified tool with the refined prompt
            result = self.use_tool(action["refined_prompt"], action["tool_index"])
        else:
            # Use the specified module to generate a response
            selected_module = self.modules[action["module_index"]]
            if self.verbose:
                print(f"Using module '{selected_module.__class__.__name__}' to process the input.")
            result = selected_module.process(user_input=action["refined_prompt"], memory=self.memory.short_term_df)

        # Store the interaction in memory
        self.store_memory(user_input, result)

        return result

    def store_memory(self, user_input: str, response: str):
        """Store the user input and response in memory."""
        self.memory.store_memory('user_input: '+ str(user_input),'response: ' + str(response))

    def get_module_by_name(self, module_name: str):
        """
        Retrieve a module instance by its class name.
        """
        for module in self.modules:
            if module.__class__.__name__ == module_name:
                return module
        return None

    def use_tool(self, user_input: str, tool_index: int) -> str:
        chosen_tool = self.toolkit.tools[tool_index]
        try:
            if chosen_tool.name == 'search':
                # You may need to parse the user_input to extract the query and n_sites
                query = user_input
                n_sites = 5  # Set default or parse from user_input
                expression = {'query_parameters': {'query': query, 'n_sites': n_sites}}
            else:
                expression = user_input

            if self.verbose:
                print(f"Using tool '{chosen_tool.name}' with expression: '{expression}'")

            result = chosen_tool.invoke(expression)
        except Exception as e:
            result = f"An error occurred while using the tool '{chosen_tool.name}': {e}"
        return result

