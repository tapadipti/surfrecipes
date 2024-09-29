<p align="center">

  <h1 align="center">SurfRecipes</h1>
    <p align="center">
    <img src="logo/SurfSlicer-512x512.jpg" alt="SurfRecipes Logo" width="200" style="border-radius: 20px;">
    </p>
  <p align="center">
    An AI agent that understands your requirements and finds suitable recipes.
</p>

## Install

```sh
pip install surfkit
```

## Quick Start

Set the 

```sh
export SPOONACULAR_API_KEY=<Provide your SPOONACULAR API KEY here>
```
If you have not created an account in Spoonacular, visit https://spoonacular.com/food-api to create and account and get your API key.

Create a tracker

```sh
surfkit create tracker -n trk101 -r docker
```

Create a device

```sh
surfkit create device -n dev101 -p qemu
```

Create the agent

```sh
surfkit create agent -n ag101 -r process --local-keys
```

Solve a task

```sh
surfkit solve "Find me a gluten-free vegetarian salad recipe with tomato and carrots and without any eggs." --agent ag101 --device dev101 --tracker trk101
```

Get the agent logs
```sh
surfkit logs --name ag101
```

Delete the agent
```sh
surfkit delete agent --name ag101
```

## Community

Come join us on [Discord](https://discord.gg/hhaq7XYPS6).
