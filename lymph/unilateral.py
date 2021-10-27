import numpy as np
from numpy.linalg import matrix_power as mat_pow
import pandas as pd
import warnings
from typing import Union, Optional, List, Dict, Any

from .node import Node, node_trans_prob
from .edge import Edge


def change_base(
    number: int, 
    base: int, 
    reverse: bool = False, 
    length: Optional[int] = None
) -> str:
    """Convert an integer into another base.
    
    Args:
        number: Number to convert
        base: Base of the resulting converted number
        reverse: If true, the converted number will be printed in reverse order.
        length: Length of the returned string. If longer than would be 
            necessary, the output will be padded.

    Returns:
        The (padded) string of the converted number.
    """
    
    if base > 16:
        raise ValueError("Base must be 16 or smaller!")
        
    convertString = "0123456789ABCDEF"
    result = ''
    while number >= base:
        result = result + convertString[number % base]
        number = number//base
    if number > 0:
        result = result + convertString[number]
        
    if length is None:
        length = len(result)
    elif length < len(result):
        length = len(result)
        warnings.warn("Length cannot be shorter than converted number.")
        
    pad = '0' * (length - len(result))
        
    if reverse:
        return result + pad
    else:
        return pad + result[::-1]



class Unilateral(object):
    """Class that models metastatic progression in a lymphatic system by 
    representing it as a directed graph. The progression itself can be modelled 
    via hidden Markov models (HMM) or Bayesian networks (BN). 
    """
    def __init__(self, graph: dict = {}):
        """Initialize the underlying graph:
        
        Args:
            graph: Every key in this dictionary is a 2-tuple containing the type of 
                the :class:`Node` ("tumor" or "lnl") and its name (arbitrary 
                string). The corresponding value is a list of names this node should 
                be connected to via an :class:`Edge`.
        """
        self.nodes = []        # list of all nodes in the graph
        self.tumors = []       # list of nodes with type tumour
        self.lnls = []         # list of all lymph node levels        
        
        for key in graph:
            self.nodes.append(Node(name=key[1], typ=key[0]))
            
        for node in self.nodes:
            if node.typ == "tumor":
                self.tumors.append(node)
            else:
                self.lnls.append(node)
        
        
        self.edges = []        # list of all edges connecting nodes in the graph
        self.base_edges = []   # list of edges, going out from tumors
        self.trans_edges = []  # list of edges, connecting LNLs

        for key, values in graph.items():
            for value in values:
                self.edges.append(Edge(self.find_node(key[1]), 
                                       self.find_node(value)))

        for edge in self.edges:
            if edge.start.typ == "tumor":
                self.base_edges.append(edge)
            else:
                self.trans_edges.append(edge)


    def __str__(self):
        """Print info about the structure and parameters of the graph.
        """
        num_tumors = len(self.tumors)
        num_lnls   = len(self.lnls)
        string = (
            f"Unilateral lymphatic system with {num_tumors} tumor(s) "
            f"and {num_lnls} LNL(s).\n"
            + " ".join([f"{e}" for e in self.edges])
        )
                
        return string


    def find_node(self, name: str) -> Union[Node, None]:
        """Finds and returns a node with name ``name``.
        """
        for node in self.nodes:
            if node.name == name:
                return node
        
        return None


    def find_edge(self, startname: str, endname: str) -> Union[Edge, None]:
        """Finds and returns the edge instance which has a parent node named 
        ``startname`` and ends with node ``endname``.
        """
        for node in self.nodes:
            if node.name == startname:
                for o in node.out:
                    if o.end.name == endname:
                        return o
                        
        return None


    def get_graph(self) -> dict:
        """Lists the graph as it was provided when the system was created.
        """
        res = []
        for node in self.nodes:
            out = []
            for o in node.out:
                out.append(o.end.name)
            res.append((node.name, out))
            
        return dict(res)


    def list_edges(self) -> List[Edge]:
        """Lists all edges of the system with its corresponding start and end 
        nodes.
        """
        res = []
        for edge in self.edges:
            res.append((edge.start.name, edge.end.name, edge.t))
            
        return res
    
    
    @property
    def state(self):
        """Return the currently set state of the system.
        """
        return np.array([lnl.state for lnl in self.lnls], dtype=bool)

    @state.setter
    def state(self, newstate: np.ndarray):
        """Sets the state of the system to ``newstate``.
        """
        if len(newstate) != len(self.lnls):
            raise ValueError("length of newstate must match # of LNLs")
        
        for i, node in enumerate(self.lnls):  # only set lnl's states
            node.state = int(newstate[i])
    
    
    @property
    def base_probs(self):
        """The spread probablities parametrizing the edges that represent the 
        lymphatic drainage from the tumor(s) to the individual lymph node 
        levels.
        
        Setting these requires an array with a length equal to the number of 
        edges in the graph that start with a tumor node. After setting these 
        values, the transition matrix - if it was precomputed - is deleted 
        so it can be recomputed with the new parameters.
        """
        return np.array([edge.t for edge in self.base_edges], dtype=float)
    
    @base_probs.setter
    def base_probs(self, new_base_probs):
        """Set the spread probabilities for the connections from the tumor to 
        the LNLs.
        """
        for i, edge in enumerate(self.base_edges):
            edge.t = new_base_probs[i]
        
        if hasattr(self, "_A"):
            del self._A


    @property
    def trans_probs(self):
        """Return the spread probablities of the connections between the lymph 
        node levels. Here, "trans" stands for "transmission" (among the LNLs), 
        not "transition" as in the transition to another state.
        
        When setting an array of length equal to the number of connections 
        among the LNL is required. After setting the new values, the transition 
        matrix - if previously computed - is deleted again, so that it will be 
        recomputed with the new parameters.
        """
        return np.array([edge.t for edge in self.trans_edges], dtype=float)
    
    @trans_probs.setter
    def trans_probs(self, new_trans_probs):
        """Set the spread probabilities for the connections among the LNLs.
        """
        for i, edge in enumerate(self.trans_edges):
            edge.t = new_trans_probs[i]
        
        if hasattr(self, "_A"):
            del self._A


    @property
    def spread_probs(self) -> np.ndarray:
        """These are the probabilities of metastatic spread. They indicate how 
        probable it is that a tumor or already cancerous lymph node level 
        spreads further along a certain edge of the graph representing the 
        lymphatic network.
        
        Setting these requires an array with a length equal to the number of 
        lymph node levels.
        """
        return np.concatenate([self.base_probs, self.trans_probs])

    @spread_probs.setter
    def spread_probs(self, new_spread_probs: np.ndarray):
        """Set the spread probabilities of the :class:`Edge` instances in the 
        the network in the order they were created from the graph.
        """
        num_base_edges = len(self.base_edges)
        
        self.base_probs = new_spread_probs[:num_base_edges]
        self.trans_probs = new_spread_probs[num_base_edges:]
            

    def comp_transition_prob(
        self, 
        newstate: List[int], 
        acquire: bool = False
    ) -> float:
        """Computes the probability to transition to ``newstate``, given its 
        current state.

        Args:
            newstate: List of new states for each LNL in the lymphatic 
                system. The transition probability :math:`t` will be computed 
                from the current states to these states.
            acquire: if ``True``, after computing and returning the probability, 
                the system updates its own state to be ``newstate``. 
                (default: ``False``)

        Returns:
            Transition probability :math:`t`.
        """
        res = 1.
        for i, lnl in enumerate(self.lnls):
            if not lnl.state:
                in_states = tuple(edge.start.state for edge in lnl.inc)
                in_weights = tuple(edge.t for edge in lnl.inc)
                res *= node_trans_prob(in_states, in_weights)[newstate[i]]

        if acquire:
            self.state = newstate

        return res


    def comp_observation_prob(
        self, 
        diagnoses_dict: Dict[str, List[int]]
    ) -> float:
        """Computes the probability to see certain diagnoses, given the 
        system's current state.

        Args:
            diagnoses_dict: Dictionary of diagnoses (one for each diagnostic 
                modality). A diagnose must be an array of integers that is as 
                long as the the system has LNLs.

        Returns:
            The probability to see the given diagnoses.
        """  
        prob = 1.
            
        for modality, diagnoses in diagnoses_dict.items():
            if len(diagnoses) != len(self.lnls):
                raise ValueError("length of observations must match # of LNLs")

            for i, lnl in enumerate(self.lnls):
                prob *= lnl.obs_prob(obs=diagnoses[i], 
                                     obstable=self._modality_tables[modality])
        return prob


    def _gen_state_list(self):
        """Generates the list of (hidden) states.
        """
        if not hasattr(self, "_state_list"):
            self._state_list = np.zeros(
                shape=(2**len(self.lnls), len(self.lnls)), dtype=int
            )
        for i in range(2**len(self.lnls)):
            self._state_list[i] = [
                int(digit) for digit in change_base(i, 2, length=len(self.lnls))
            ]
    
    @property
    def state_list(self):
        """Return list of all possible hidden states. They are arranged in the 
        same order as the lymph node levels in the network/graph."""
        try:
            return self._state_list
        except AttributeError:
            self._gen_state_list()
            return self._state_list


    def _gen_obs_list(self):
        """Generates the list of possible observations.
        """
        n_obs = len(self._modality_tables)
        
        if not hasattr(self, "_obs_list"):
            self._obs_list = np.zeros(
                shape=(2**(n_obs * len(self.lnls)), n_obs * len(self.lnls)), 
                dtype=int
            )
        
        for i in range(2**(n_obs * len(self.lnls))):
            tmp = change_base(i, 2, reverse=False, length=n_obs * len(self.lnls))
            for j in range(len(self.lnls)):
                for k in range(n_obs):
                    self._obs_list[i,(j*n_obs)+k] = int(tmp[k*len(self.lnls)+j])
    
    @property
    def obs_list(self):
        """Return the list of all possible observations.
        """
        try:
            return self._obs_list
        except AttributeError:
            self._gen_obs_list()
            return self._obs_list


    def _gen_mask(self):
        """
        Generates a dictionary that contains for each row of 
        :math:`\\mathbf{A}` those indices where :math:`\\mathbf{A}` is NOT zero.
        """
        self._mask = {}
        for i in range(len(self.state_list)):
            self._mask[i] = []
            for j in range(len(self.state_list)):
                if not np.any(np.greater(self.state_list[i,:], 
                                         self.state_list[j,:])):
                    self._mask[i].append(j)
    
    @property
    def mask(self):
        """Return a dictionary with keys for each possible hidden state. The 
        respective value is then a list of all hidden state indices that can be 
        reached from that key's state. This allows the model to skip the 
        expensive computation of entries in the transition matrix that are zero 
        anyways, because self-healing is forbidden.
        
        For example: The hidden state ``[True, True, False]`` in a network 
        with only one tumor and two LNLs (one involved, one healthy) corresponds 
        to the index ``1`` and can only evolve into the state 
        ``[True, True, True]``, which has index 2. So, the key-value pair for 
        that particular hidden state would be ``1: [2]``.
        """
        try:
            return self._mask
        except AttributeError:
            self._gen_mask()
            return self._mask


    def _gen_A(self):
        """
        Generates the transition matrix :math:`\\mathbf{A}`, which contains 
        the :math:`P \\left( X_{t+1} \\mid X_t \\right)`. :math:`\\mathbf{A}` 
        is a square matrix with size ``(# of states)``. The lower diagonal is 
        zero.
        """
        if not hasattr(self, "_A"):
            self._A = np.zeros(shape=(2**len(self.lnls), 2**len(self.lnls)))
        
        for i,state in enumerate(self.state_list):
            self.state = state
            for j in self.mask[i]:
                self._A[i,j] = self.comp_transition_prob(self.state_list[j])
    
    @property
    def A(self):
        """Return the transition matrix :math:`\\mathbf{A}`, which contains the 
        probability to transition from any state to any other state within one 
        time-step :math:`P \\left( X_{t+1} \\mid X_t \\right)`. 
        :math:`\\mathbf{A}` is a square matrix with size ``(# of states)``. The 
        lower diagonal is zero, because self-healing is forbidden.
        """
        try:
            return self._A
        except AttributeError:
            self._gen_A()
            return self._A

    
    @property
    def modalities(self):
        """Return specificity & sensitivity stored in this :class:`System` for 
        every diagnostic modality that has been defined.
        """
        try:
            modality_spsn = {}
            for mod, table in self._modality_tables.items():
                modality_spsn[mod] = [table[0,0], table[1,1]]
            return modality_spsn
        
        except AttributeError:
            msg = ("No modality defined yet with specificity & sensitivity.")
            warnings.warn(msg)
            return {}

    
    @modalities.setter
    def modalities(self, modality_spsn: Dict[Any, List[float]]):
        """Given specificity :math:`s_P` & sensitivity :math:`s_N` of different 
        diagnostic modalities, create a 2x2 matrix for every disgnostic 
        modality that stores 
        
        .. math::
            \\begin{pmatrix}
            s_P & 1 - s_N \\\\
            1 - s_P & s_N
            \\end{pmatrix}
        """
        self._modality_tables = {}
        for mod, spsn in modality_spsn.items():
            if not isinstance(mod, str):
                msg = ("Modality names must be strings.")
                raise TypeError(msg)
            
            has_len_2 = len(spsn) == 2
            is_above_lb = np.all(np.greater_equal(spsn, 0.5))
            is_below_ub = np.all(np.less_equal(spsn, 1.))
            if not has_len_2 or not is_above_lb or not is_below_ub:
                msg = ("For each modality provide a list of two decimals "
                       "between 0.5 and 1.0 as specificity & sensitivity "
                       "respectively.")
                raise ValueError(msg)
            
            sp, sn = spsn
            self._modality_tables[mod] = np.array([[sp     , 1. - sn],
                                                   [1. - sp, sn     ]])


    def _gen_B(self):
        """Generates the observation matrix :math:`\\mathbf{B}`, which contains 
        the :math:`P \\left(Z_t \\mid X_t \\right)`. :math:`\\mathbf{B}` has the 
        shape ``(# of states, # of possible observations)``.
        """
        n_lnl = len(self.lnls)
        
        if not hasattr(self, "_B"):
            self._B = np.zeros(shape=(len(self.state_list), len(self.obs_list)))
        
        for i,state in enumerate(self.state_list):
            self.state = state
            for j,obs in enumerate(self.obs_list):
                diagnoses_dict = {}
                for k,modality in enumerate(self._modality_tables):
                    diagnoses_dict[modality] = obs[n_lnl * k : n_lnl * (k+1)]
                self._B[i,j] = self.comp_observation_prob(diagnoses_dict)
    
    @property
    def B(self):
        """Return the observation matrix."""
        try:
            return self._B
        except AttributeError:
            self._gen_B()
            return self._B 


    def _gen_C(
        self,
        table: np.ndarray,
        t_stage: Optional[str] = None,
        delete_ones: bool = True,
        aggregate_duplicates: bool = True
    ):
        """Generate data matrix :math:`\\mathbf{C}` for every T-stage that 
        marginalizes over complete observations when a patient's diagnose is 
        incomplete.
        
        Args:
            table: 2D array where rows represent patients (of the same T-stage) 
                and columns are LNL involvements.
            
            t_stage: T-stage for which to compute the data matrix. Should only 
                be provided for the ``"HMM"`` model.
            
            delete_ones: If ``True``, columns in the :math:`\\mathbf{C}` matrix 
                that contain only ones (meaning the respective diagnose is 
                completely unknown) are removed, since they only add zeros to 
                the log-likelihood.
                
            aggregate_duplicates: If ``True``, the number of occurences of 
                diagnoses in the :math:`\\mathbf{C}` matrix is counted and 
                collected in a vector :math:`\\mathbf{f}`. The duplicate 
                columns are then deleted.  
            
        :meta public:     
        """
        if not hasattr(self, "_C") or not hasattr(self, "_f"):
            self._C = {}
            self._f = {}
        
        if t_stage is None:
            # T-stage is not provided, when mode is "BN".
            t_stage = "BN"
        
        tmp_C = np.zeros(shape=(len(self.obs_list), len(table)), dtype=bool)
        for i,row in enumerate(table):
            for j,obs in enumerate(self.obs_list):
                # save whether all not missing observations match or not
                tmp_C[j,i] = np.all(
                    np.equal(obs, row, 
                             where=~np.isnan(row.astype(float)),
                             out=np.ones_like(row, dtype=bool))
                )
                
        if delete_ones:
            sum_over_C = np.sum(tmp_C, axis=0)
            keep_idx = np.argwhere(sum_over_C != len(self.obs_list)).flatten()
            tmp_C = tmp_C[:,keep_idx]
            
        if aggregate_duplicates:
            tmp_C, tmp_f = np.unique(tmp_C, axis=1, return_counts=True)
        else:
            tmp_f = np.ones(shape=len(table), dtype=int)
        
        self._C[t_stage] = tmp_C.copy()
        self._f[t_stage] = tmp_f.copy()
    
    @property
    def C(self) -> Dict[str, np.ndarray]:
        """Return the dictionary containing data matrices for each T-stage.
        """
        try:
            return self._C
        except AttributeError:
            msg = ("No data was loaded yet.")
            raise AttributeError(msg)
    
    @property
    def f(self) -> Dict[str, np.ndarray]:
        """Return the frequency vector containing the number of occurences of 
        patients.
        """
        try:
            return self._f
        except AttributeError:
            msg = ("No data was loaded yet.")
            raise AttributeError(msg)


    def load_data(
        self,
        data: pd.DataFrame, 
        t_stages: Optional[List[int]] = None, 
        modality_spsn: Optional[Dict[str, List[float]]] = None, 
        mode: str = "HMM",
        gen_C_kwargs: dict = {'delete_ones': True, 
                              'aggregate_duplicates': True}
    ):
        """
        Transform tabular patient data (:class:`pd.DataFrame`) into internal 
        representation, consisting of one or several matrices 
        :math:`\\mathbf{C}_{T}` that can marginalize over possible diagnoses.

        Args:
            data: Table with rows of patients. Must have a two-level 
                :class:`MultiIndex` where the top-level has categories 'Info' 
                and the name of the available diagnostic modalities. Under 
                'Info', the second level is only 'T-stage', while under the 
                modality, the names of the diagnosed lymph node levels are 
                given as the columns.

            t_stages: List of T-stages that should be included in the learning 
                process. If ommitted, the list of T-stages is extracted from 
                the :class:`DataFrame`

            modality_spsn: Dictionary of specificity :math:`s_P` and :math:`s_N` 
                (in that order) for each observational/diagnostic modality. Can 
                be ommitted if the modalities where already defined.

            mode: `"HMM"` for hidden Markov model and `"BN"` for Bayesian net.
                
            gen_C_kwargs: Keyword arguments for the :meth:`_gen_C`. For 
                efficiency, both ``delete_ones`` and ``aggregate_duplicates``
                should be set to one, resulting in a smaller :math:`\\mathbf{C}` 
                matrix and an additional count vector :math:`\\mathbf{f}`.
        """
        if modality_spsn is not None:
            self.modalities = modality_spsn
        elif self.modalities == {}:
            msg = ("No diagnostic modalities have been defined yet!")
            raise ValueError(msg)
        
        # For the Hidden Markov Model
        if mode=="HMM":
            if t_stages is None:
                t_stages = list(set(data[("Info", "T-stage")]))

            for stage in t_stages:
                table = data.loc[data[('Info', 'T-stage')] == stage,
                                 self._modality_tables.keys()].values
                self._gen_C(table, stage, **gen_C_kwargs)

        # For the Bayesian Network
        elif mode=="BN":
            table = data[self._modality_tables.keys()].values
            self._gen_C(table, **gen_C_kwargs)


    def _evolve(
        self, t_first: int = 0, t_last: Optional[int] = None
    ) -> np.ndarray:
        """Evolve hidden Markov model based system over time steps. Compute 
        :math:`p(S \\mid t)` where :math:`S` is a distinct state and :math:`t` 
        is the time.
        
        Args:
            t_first: First time-step that should be in the list of returned 
                involvement probabilities.
            
            t_last: Last time step to consider. This function computes 
                involvement probabilities for all :math:`t` in between `t_frist` 
                and `t_last`. If `t_first == t_last`, "math:`p(S \\mid t)` is 
                computed only at that time.
        
        Returns:
            A matrix with the values :math:`p(S \\mid t)` for each time-step.
        
        :meta public:
        """
        # All healthy state at beginning
        start_state = np.zeros(shape=len(self.state_list), dtype=float)
        start_state[0] = 1.
        
        # compute involvement at first time-step
        state = start_state @ mat_pow(self.A, t_first)
        
        if t_last is None:
            return state
        
        len_time_range = t_last - t_first
        if len_time_range < 0:
            msg = ("Starting time must be smaller than ending time.")
            raise ValueError(msg)
        
        state_probs = np.zeros(
            shape=(len_time_range + 1, len(self.state_list)), 
            dtype=float
        )
        
        # compute subsequent time-steps, effectively incrementing time until end
        for i in range(len_time_range):
            state_probs[i] = state
            state = state @ self.A
        
        state_probs[-1] = state
        
        return state_probs


    def _spread_probs_are_valid(self, new_spread_probs: np.ndarray) -> bool:
        """Check that the spread probability (rates) are all within limits.
        """
        if new_spread_probs.shape != self.spread_probs.shape:
            msg = ("Shape of provided spread parameters does not match network")
            raise ValueError(msg)
        if np.any(np.greater(0., new_spread_probs)):
            return False
        if np.any(np.greater(new_spread_probs, 1.)):
            return False
        
        return True
    

    def log_likelihood(
        self,
        spread_probs: np.ndarray,
        t_stages: Optional[List[Any]] = None,
        diag_times: Optional[Dict[Any, int]] = None,
        max_t: Optional[int] = 10,
        time_dists: Optional[Dict[Any, np.ndarray]] = None,
        mode: str = "HMM"
    ) -> float:
        """
        Compute log-likelihood of (already stored) data, given the spread 
        probabilities and either a discrete diagnose time or a distribution to 
        use for marginalization over diagnose times.
        
        Args:
            spread_probs: Spread probabiltites from the tumor to the LNLs, as 
                well as from (already involved) LNLs to downsream LNLs.
            
            t_stages: List of T-stages that are also used in the data to denote 
                how advanced the primary tumor of the patient is. This does not 
                need to correspond to the clinical T-stages 'T1', 'T2' and so 
                on, but can also be more abstract like 'early', 'late' etc. If 
                not given, this will be inferred from the loaded data.
            
            diag_times: For each T-stage, one can specify with what time step 
                the likelihood should be computed. If this is set to `None`, 
                and a distribution over diagnose times `time_dists` is provided, 
                the function marginalizes over diagnose times.
            
            max_t: Latest possible diagnose time. This is only used to return 
                `-np.inf` in case one of the `diag_times` exceeds this value.
            
            time_dists: Distribution over diagnose times that can be used to 
                compute the likelihood of the data, given the spread 
                probabilities, but marginalized over the time of diagnosis. If 
                set to `None`, a diagnose time must be explicitly set for each 
                T-stage.
            
            mode: Compute the likelihood using the Bayesian network (`"BN"`) or 
                the hidden Markv model (`"HMM"`). When using the Bayesian net, 
                the inputs `t_stages`, `diag_times`, `max_t` and `time_dists` 
                are ignored.
        
        Returns:
            The log-likelihood :math:`\\log{p(D \\mid \\theta)}` where :math:`D` 
            is the data and :math:`\\theta` is the tuple of spread probabilities 
            and diagnose times or distributions over diagnose times.
        """
        if not self._spread_probs_are_valid(spread_probs):
            return -np.inf
        
        self.spread_probs = spread_probs
        
        # hidden Markov model
        if mode == "HMM":
            if t_stages is None:
                t_stages = list(self.f_dict.keys())
                
            state_probs = {}
            
            if diag_times is not None:
                if len(diag_times) != len(t_stages):
                    msg = ("One diagnose time must be provided for each T-stage.")
                    raise ValueError(msg)
                
                for stage in t_stages:
                    diag_time = np.around(diag_times[stage]).astype(int)
                    if diag_time > max_t:
                        return -np.inf
                    state_probs[stage] = self._evolve(diag_time)
                
            elif time_dists is not None:
                if len(time_dists) != len(t_stages):
                    msg = ("One distribution over diagnose times must be provided "
                        "for each T-stage.")
                    raise ValueError(msg)
                
                # subtract 1, to also consider healthy starting state (t = 0)
                max_t = len(time_dists[t_stages[0]]) - 1
                
                for stage in t_stages:
                    state_probs[stage] = time_dists[stage] @ self._evolve(t_last=max_t)
                
            else:
                msg = ("Either provide a list of diagnose times for each T-stage "
                    "or a distribution over diagnose times for each T-stage.")
                raise ValueError(msg)
            
            llh = 0.
            for stage in t_stages:
                p = state_probs[stage] @ self.B @ self.C[stage]
                llh += self.f[stage] @ np.log(p)
        
        # likelihood for the Bayesian network
        elif mode == "BN":
            a = np.ones(shape=(len(self.state_list),), dtype=float)

            for i, state in enumerate(self.state_list):
                self.state = state
                for node in self.lnls:
                    a[i] *= node.bn_prob()

            b = a @ self.B
            llh = self.f["BN"] @ np.log(b @ self.C["BN"])
        
        return llh


    def marginal_log_likelihood(
        self, 
        theta: np.ndarray, 
        t_stages: Optional[List[Any]] = None, 
        time_dists: Dict[Any, np.ndarray] = {}
    ) -> float:
        """
        Compute the likelihood of the (already stored) data, given the spread 
        parameters, marginalized over time of diagnosis via time distributions.

        Args:
            theta: Set of parameters, consisting of the base probabilities 
                :math:`b` (as many as the system has nodes) and the transition 
                probabilities :math:`t` (as many as the system has edges).

            t_stages: List of T-stages that should be included in the learning 
                process.

            time_dists: Distribution over the probability of diagnosis at 
                different times :math:`t` given T-stage.

        Returns:
            The log-likelihood of the data, given te spread parameters.
        """
        return self.log_likelihood(
            theta, t_stages,
            diag_times=None, time_dists=time_dists,
            mode="HMM"
        )


    def time_log_likelihood(
        self, 
        theta: np.ndarray, 
        t_stages: List[Any],
        max_t: int = 10
    ) -> float:
        """
        Compute likelihood given the spread parameters and the time of diagnosis 
        for each T-stage.
        
        Args:
            theta: Set of parameters, consisting of the spread probabilities 
                (as many as the system has :class:`Edge` instances) and the 
                time of diagnosis for all T-stages.
                
            t_stages: keywords of T-stages that are present in the dictionary of 
                C matrices and the previously loaded dataset.
            
            max_t: Largest accepted time-point.
            
        Returns:
            The likelihood of the data, given the spread parameters as well as 
            the diagnose time for each T-stage.
        """
        # splitting theta into spread parameters and...
        len_spread_probs = len(theta) - len(t_stages)
        spread_probs = theta[:len_spread_probs]
        # ...diagnose times for each T-stage
        tmp = theta[len_spread_probs:]
        diag_times = {t_stages[t]: tmp[t] for t in range(len(t_stages))}
        
        return self.log_likelihood(
            spread_probs, t_stages,
            diag_times=diag_times, max_t=max_t, time_dists=None,
            mode="HMM"
        )

    
    def risk(
        self,
        spread_probs: Optional[np.ndarray] = None,
        inv: Optional[np.ndarray] = None,
        diagnoses: Dict[str, np.ndarray] = {},
        diag_time: Optional[int] = None,
        time_dist: Optional[np.ndarray] = None,
        mode: str = "HMM"
    ) -> Union[float, np.ndarray]:
        """
        Compute risk(s) of involvement given a specific (but potentially 
        incomplete) diagnosis.
        
        Args:
            spread_probs: Set of new spread parameters. If not given (``None``),
                the currently set parameters will be used.
                
            inv: Specific hidden involvement one is interested in. If only parts 
                of the state are of interest, the remainder can be masked with 
                values ``None``. If specified, the functions returns a single 
                risk.
                
            diagnoses: Dictionary that can hold a potentially incomplete (mask 
                with ``None``) diagnose for every available modality. Leaving 
                out available modalities will assume a completely missing 
                diagnosis.
                
            diag_time: Time of diagnosis. Either this or the `time_dist` to 
                marginalize over diagnose times must be given.
                
            time_dist: Distribution to marginalize over diagnose times. Either 
                this, or the `diag_time` must be given.
                
            mode: Set to ``"HMM"`` for the hidden Markov model risk (requires 
                the ``time_dist``) or to ``"BN"`` for the Bayesian network 
                version.
                
        Returns:
            A single probability value if ``inv`` is specified and an array 
            with probabilities for all possible hidden states otherwise.
        """
        # assign spread_probs to system or use the currently set one
        if spread_probs is not None:
            self.spread_probs = spread_probs
            
        # create one large diagnose vector from the individual modalitie's 
        # diagnoses
        obs = np.array([])
        for mod in self._modality_tables:
            if mod in diagnoses:
                obs = np.append(obs, diagnoses[mod])
            else:
                obs = np.append(obs, np.array([None] * len(self.lnls)))
        
        # vector of probabilities of arriving in state x, marginalized over time
        # HMM version
        if mode == "HMM":
            if diag_time is not None:
                pX = self._evolve(diag_time)
                
            elif time_dist is not None:
                max_t = len(time_dist)
                state_probs = self._evolve(t_last=max_t-1)
                pX = time_dist @ state_probs
            
            else:
                msg = ("Either diagnose time or distribution to marginalize "
                       "over it must be given.")
                raise ValueError(msg)
                
        # BN version
        elif mode == "BN":
            pX = np.ones(shape=(len(self.state_list)), dtype=float)
            for i, state in enumerate(self.state_list):
                self.state = state
                for node in self.lnls:
                    pX[i] *= node.bn_prob()
        
        # compute the probability of observing a diagnose z and being in a 
        # state x which is P(z,x) = P(z|x)P(x). Do that for all combinations of 
        # x and z and put it in a matrix
        pZX = self.B.T * pX
        
        # vector of probabilities for seeing a diagnose z
        pZ = pX @ self.B
        
        # build vector to marginalize over diagnoses
        cZ = np.zeros(shape=(len(pZ)), dtype=bool)
        for i,complete_obs in enumerate(self.obs_list):
            cZ[i] = np.all(np.equal(obs, complete_obs, 
                                    where=(obs!=None),
                                    out=np.ones_like(obs, dtype=bool)))
        
        # compute vector of probabilities for all possible involvements given 
        # the specified diagnosis
        res =  cZ @ pZX / (cZ @ pZ)
        
        if inv is None:
            return res
        else:
            # if a specific involvement of interest is provided, marginalize the 
            # resulting vector of hidden states to match that involvement of 
            # interest
            inv = np.array(inv)
            cX = np.zeros(shape=res.shape, dtype=bool)
            for i,state in enumerate(self.state_list):
                cX[i] = np.all(np.equal(inv, state, 
                                        where=(inv!=None),
                                        out=np.ones_like(state, dtype=bool)))
            return cX @ res



class System(Unilateral):
    """Class kept for compatibility after renaming to :class:`Unilateral`.
    
    See Also:
        :class:`Unilateral`
    """
    def __init__(self, *args, **kwargs):
        msg = ("This class has been renamed to `Unilateral`.")
        warnings.warn(msg, DeprecationWarning)
        
        super().__init__(*args, **kwargs)