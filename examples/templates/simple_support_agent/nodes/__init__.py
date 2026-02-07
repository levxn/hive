"""Node definitions for simple_support_agent."""

from framework.graph import NodeSpec
# Customer Intake
intake_node = NodeSpec(
    id="intake",
    name="Customer Intake",
    description="Gather customer inquiry details",
    node_type="event_loop",
    client_facing=False,
    input_keys=[],
    output_keys=[],
    system_prompt="""You are a helpful customer support agent. Gather information about the customer's issue.""",)
# Response Generator
response_node = NodeSpec(
    id="response",
    name="Response Generator",
    description="Generate helpful response",
    node_type="event_loop",
    client_facing=False,
    input_keys=[],
    output_keys=[],
    system_prompt="""You are a helpful customer support agent. Provide a clear, helpful response to the customer.""",)