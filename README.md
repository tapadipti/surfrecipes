# RecipeFinder

An AI agent that understands your requirements and finds suitable recipes

## Install
```sh
pip install surfkit
```

## Usage

Create an agent
```sh
surfkit create agent -f ./agent.yaml --runtime { process | docker | kube } --name foo
```

List running agents
```sh
surfkit list agents
```

Use the agent to solve a task
```sh
surfkit solve --agent foo --description "Find me a gluten-free vegetarian soup recipe with tomato and carrots and without any eggs." --device-type desktop
```

Get the agent logs
```sh
surfkit logs --name foo
```

Delete the agent
```sh
surfkit delete agent --name foo
```

