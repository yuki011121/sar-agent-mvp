import pytest
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.metrics import GEval

'''
Testing history agent RAG using GEval for task-specific
metrics and takes into account semantic meanings of LLM
outputs
'''



#sub to history out 

#loop
    #send history agent the payload
    #next(generator)
    #run GEval