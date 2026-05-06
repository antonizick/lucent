

Initial
----------------

OK You and I are going to collaborating on building my new AI assist end partner . We are going to utilize the basic framework concepts in the shared-brain files, But we are going to evolve it and make it our own.

  I want my identity file to be called:
  lucentIdent.md - This is where we will store expected personalities, actions , behaviors, habits for Lucent (my AI assistent), This should  Automatically populated and maintained by the agent , although there are times I may
  direct the agent to perform some specific updates to this file

  My Identity file should be called userIdent.md - This is where information about will be kept , facts about me , my expectations , preferences and habits - This should also be automatically populated and maintained by the
  agent although there are times I may direct the agent to perform some specific updates to this file

  LTMemory.md Is where long term will accumulate , this will be agent populated over time curating and summarizing our daily episodic notes.

  core.md Is the startup and ritual for Lucent as well as all other AI agents we activate it will outline the core rules and requirements they need to operate , it will not dictate personality and objective, that will be done
  either by lucentIdent.md file (For the main identity ) Or sub agents we build will have their own identity files

  There should be a directory called memory. COntained in this folder will be a series of daily notes files that are formatted ( yyyy-mm-dd.md )   These files will effectively a detailed short term memory summary of daily
  activity  And tasks between the AI agents and I. It is not a transcript file , but rather a living summary document . Periodically these will be reviewed and used curate, update and prune the LTMemory.md File we discussed
  above.  These files should not be deleted  , but rather aggregate overtime so that if we want to ask a very detailed question about work that was done in the past that information will always be there

  There sould be a directory called agents. Contained in this folder will be a series of files whose names are formatted {agent name}-agent.md This is where we will store the expected personalities , actions, behaviors, habits
  and principal objectives for sub agent AI Personalities that can be invoked by Lucent.  That way Lucent (or I) Can invoke an AI agent with new context window that leverage core.md file (discussed above) and it's own [agent
  name}-agent.md file that will allow the agent to give a targeted purpose based  Existence with the background context without any additional session context


  Right now that's all I have planned for the basic file structure


  Ultimately I would like this agentic AI to run , I will either be using ClaudeCode or OpenCode (TBD) The AG AII Choose should not maintain session in memory only, But constantly be required to summarize and update the app
  memory.md documents.

   I want to establish a private Github repository where all of these files and all of this work is synchronized daily

  Eventually I would like to build a web UI to manage the interaction with the agent and all of its sub agents . I would like to have both voice recognition and speech to text eventually , preferably when Lucent speaks to me
  Have some sort of very cool high tech animation associated with that

  currently my Projects all live within directory /home/nick/dev/{project sub-directory}  (Including this project). An open question I have is if I want Lucent to be my collaborator and work on different projects with me, Where
  do I need to run Lucent from? Does it need to be something outside of the /home/nick/dev/{poject subdirectory } Folder structure ?

  Also, preserve and leave the folder ai-shared-brain Alone... that is our model and inspiration only . Everything we build should be in the lucent project folder we are operating out of.   Whether we build and workout of the root directory here or create a subdirectory is up for discussion, What do you think or recommend? 

---------------------

