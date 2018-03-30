import datetime
import json

class TrialHelper(object):
    @staticmethod
    def _check_type(trials):
        if not isinstance(trials, list):
            raise ValueError("The input must be an instance of list")
        if not reduce( lambda x, y: x & y, map(lambda trial: isinstance(trial, Trial), trials) ):
            raise ValueError("The input contains elements which are not instances of Trial")

    @staticmethod
    def _pass_fail_check(trial):
        return trial.ds["status"] == "valid"

    @staticmethod
    def load(filename):
        with open(filename, "r") as f:
            jsonobjs = json.load(f)

        trials = []
        for jsonobj in jsonobjs:
            trial = Trial()
            trial.ds = jsonobj
            trials.append(trial)

        return trials

    @staticmethod
    def categorize_in(trials, name):
        trials_cat = {}
        for trial in trials:
            key = trial.ds[name]
            if not key in trials_cat.keys():
                trials_cat[key] = []

            trials_cat[key].append(trial)

        return trials_cat

    @staticmethod
    def to_json(trials):
        TrialHelper._check_type(trials)
        return json.dumps( map(lambda trial: trial.ds, trials), indent=4 )

    @staticmethod
    def pass_fail_list(trials, check_func=None):
        TrialHelper._check_type(trials)
        if not check_func:
            check_func = TrialHelper._pass_fail_check
        return map(check_func, trials)


class Trial(object):
    def __init__(self, taskname=None):
        self.ds = {
            "task": taskname,
            "timestamp": str(datetime.datetime.now()),
            "status": "valid",
            "error-msg": None,
            "extra": None
        }

    def put_extra(self, name, value):
        if self.ds["extra"] == None:
            self.ds["extra"] = {}

        self.ds["extra"][name] = value

    def invalidate(self, errormsg):
        self.ds["status"] = "invalid"
        self.ds["error-msg"] = errormsg
