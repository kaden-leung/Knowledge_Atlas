# Classifier Result Boxology

```text
+---------------------+       +---------------------+
| Submitted article   | ----> | Classifier payload  |
+---------------------+       +---------------------+
                                      |
                                      v
                              +---------------------+
                              | Classifier response |
                              | score + verdict     |
                              +---------------------+
                                      |
                                      v
                              +---------------------+
                              | Page result section |
                              | student can inspect |
                              +---------------------+
```

The boxology makes the contract explicit: classifier output must return to the page as a readable result/verdict, not only disappear into storage.
