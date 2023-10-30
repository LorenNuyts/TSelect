import time
import warnings
from abc import ABC, abstractmethod
from typing import Union, Dict

import pandas as pd

from tsfilter.filters.minirocketfilter import MiniRocketFilter
from tsfilter.utils import *
from tsfilter.utils.constants import SEED, Keys
from tsfilter.utils.scaler import MinMaxScaler3D
from tsfuse.computation import Input
from tsfuse.construction.mlj20 import TSFuseExtractor
from tsfuse.data import dict_collection_to_pd_multiindex, Collection


class AbstractFilter(ABC):
    """
    An abstract class for filters. It contains the basic functionality that all filters should have.
    """
    def __init__(self, series_fusion: bool = True,
                 irrelevant_filter=True,
                 redundant_filter=True,
                 optimized: bool = False,
                 auc_percentage: float = 0.75,
                 auc_threshold: float = 0.5,
                 corr_threshold: float = 0.7,
                 test_size: float = 0.2,
                 views: List[int] = None,
                 add_tags=lambda x: x,
                 compatible=lambda x: x,
                 task: str = 'auto',
                 random_state: int = SEED, ):
        """
        The constructor for AbstractFilter class.

         Parameters
        ----------
        series_fusion : bool, optional, default False
            Whether to derive new signals from the original ones ("fusion").
        irrelevant_filter : bool, optional, default False
            Whether to filter out irrelevant signals ("irrelevant filter").
        redundant_filter : bool, optional, default False
            Whether to filter out redundant signals ("redundant filter").
        optimized : bool, optional, default False
            Whether to use the optimized version for computing rank correlations in the redundant filter.
        auc_percentage : float, optional, default 0.75
            The percentage of the time series that will remain after the irrelevant filter. If the auc_threshold is
            0.75, the 75% time series with the highest AUC will remain.
        auc_threshold : float, optional, default 0.5
            The threshold for the irrelevant filter. If the auc_threshold is 0.5, all series with an AUC lower than
            0.5 will be removed, regardless of the specified auc_percentage. After all signals with an AUC lower than
            this threshold are removed, the auc_percentage will be applied.
        corr_threshold : float, optional, default 0.7
            The threshold used for clustering rank correlations. All predictions with a rank correlation above this
             threshold are considered correlated.
        test_size : float, optional, default 0.2
            The test size to use for filtering out irrelevant series based on their AUC score. The test size is the
            percentage of the data that is used for computing the AUC score. The remaining data is used for training.
            If None, the train size is derived from max(100, 0.25*nb_instances). The test size are then the remaining
            instances.
        views : list of int, optional, default None
             The different views of the data. This parameter is used to convert to the internal TSFuse Collection
             format, that groups the dimensions of the data in the unique sensors. For more information on this,
             we refer to https://github.com/arnedb/tsfuse
        add_tags: Callable, default=lambda x: x
            A function that adds tags to the data. This parameter is used to convert to the internal TSFuse Collection
            and adds tags to the Collection, describing what sensors were used for the different dimensions.
            For more information on this, we refer to https://github.com/arnedb/tsfuse
        compatible: Callable, default=lambda x: x
            A function that adds tags to the data. This parameter is used to convert to the internal TSFuse Collection
            and describes what dimensions can be combined to derive new series. For more information on this,
            we refer to https://github.com/arnedb/tsfuse
        task: str, default='auto'
            The task to perform. Can be either 'auto', 'classification' or 'regression'. If 'auto', the task is inferred
            from the data.
        random_state : int, optional, default SEED
            The random state used throughout the class.
        """
        self.series_fusion = series_fusion
        self.irrelevant_filter = irrelevant_filter
        self.redundant_filter = redundant_filter
        self.series_filtering = irrelevant_filter or redundant_filter
        self.optimized = optimized
        self.auc_percentage = auc_percentage
        self.auc_threshold = auc_threshold
        self.corr_threshold = corr_threshold
        self.test_size = test_size
        self.views = views
        self.add_tags = add_tags
        self.compatible = compatible
        self.task = task
        self.random_state = random_state

        self.tsfuse_extractor = TSFuseExtractor(transformers='full', compatible=compatible, random_state=SEED)
        self.series_filter = self.__init_filter__()
        if self.series_filtering:
            self.tsfuse_extractor.series_filter = self.series_filter

        self.included_inputs = []
        self.nodes_translation = {}

    def __init_filter__(self):
        """
        Initialize the filter. This function is called in the constructor and should be implemented by the child class
        if non-default behavior is required (default behavior is the MiniRocketFilter).
        """
        return MiniRocketFilter(irrelevant_filter=self.irrelevant_filter, redundant_filter=self.redundant_filter,
                                num_kernels=100, random_state=SEED, optimized=self.optimized,
                                auc_percentage=self.auc_percentage, filtering_threshold_corr=self.corr_threshold,
                                filtering_test_size=self.test_size) if self.series_filtering else None

    def transform_fusion(self, X_tsfuse: Dict[Union[str, int], Collection]) -> Dict[Union[str, int], Collection]:
        """
        Transform the data by fusing the series. This function is called in the transform function and should be
        implemented by the child class if non-default behavior is required.

        Parameters
        ----------
        X_tsfuse : Dict[Union[str, int], Collection]
            The data to transform in the TSFuse format.

        Returns
        -------
        X_tsfuse : Dict[Union[str, int], Collection]
            The transformed data in the TSFuse format.
        """
        dict_collection = self.tsfuse_extractor.transform(X_tsfuse, return_dataframe=False)
        dict_collection = {self.nodes_translation[k]: v for k, v in dict_collection.items()}
        inputs = {f'Input({i.name})': X_tsfuse[i.name] for i in self.included_inputs}
        dict_collection.update(inputs)
        if isinstance(self.series_filter, MiniRocketFilter):
            dict_collection = self.series_filter.scaler.transform(dict_collection)
        return dict_collection

    def transform_filter(self, X: Union[pd.DataFrame, Dict[Union[str, int], Collection]]):
        """
        Transform the data by filtering the series. This function is called in the transform function and should be
        implemented by the child class if non-default behavior is required.

        Parameters
        ----------
        X : pd.DataFrame or Dict[Union[str, int], Collection]
            The data to transform in the MultiIndex Pandas or TSFuse format.

        Returns
        -------
        X : pd.DataFrame or Dict[Union[str, int], Collection]
            The transformed data in the MultiIndex Pandas or TSFuse format.
        """
        if isinstance(X, pd.DataFrame):
            rename_columns_pd(X, self.nodes_translation)
        elif isinstance(X, dict):
            X = rename_keys_dict(X, self.nodes_translation)
        return self.series_filter.transform(X)

    @abstractmethod
    def transform_model(self, X):
        """
        Transform the data by applying the model. This function is called in the transform function and should be
        implemented by the child class.

        Parameters
        ----------
        X : pd.DataFrame
            The data to transform in the MultiIndex Pandas format.

        Returns
        -------
        X : pd.DataFrame
            The transformed data in the MultiIndex Pandas format.
        """
        pass

    def transform(self, X: Union[pd.DataFrame, Dict[Union[str, int], Collection]]):
        """
        Transform the data by applying fusion, filtering and the model.

        Parameters
        ----------
        X : Union[pd.DataFrame, Dict[Union[str, int], Collection]]
            The data to transform in the MultiIndex Pandas format or the TSFuse format.

        Returns
        -------
        X : pd.DataFrame
            The transformed data in the MultiIndex Pandas format.
        """
        if isinstance(X, pd.DataFrame):
            X_pd = X
            X_tsfuse = None
        else:
            X_pd = None
            X_tsfuse = X
        if self.series_fusion:
            if not X_tsfuse:
                X_tsfuse = get_tsfuse_format(X, views=self.views, add_tags=self.add_tags)
            X_tsfuse = self.transform_fusion(X_tsfuse)
            X_pd = dict_collection_to_pd_multiindex(X_tsfuse, index=X_pd.index if X_pd is not None else None)

        if self.series_filter and (not self.series_fusion):
            # If the series are fused, the tsfuse extractor takes care of only returning the filtered series
            X = self.transform_filter(X)
            if isinstance(X, dict):
                X_pd = dict_collection_to_pd_multiindex(X, index=X_pd.index if X_pd is not None else None)

        if X_pd is None:
            X_pd = dict_collection_to_pd_multiindex(X_tsfuse)
        return self.transform_model(X_pd)

    @abstractmethod
    def fit_model(self, X, y):
        """
        Fit the model. This function is called in the fit function and should be implemented by the child class.

        Parameters
        ----------
        X : pd.DataFrame
            The data to fit in the MultiIndex Pandas format.
        y : pd.Series
            The target variable.

        Returns
        -------
        None, but the model should be fitted.
        """
        pass

    def fit(self, X: Union[pd.DataFrame, Dict[Union[str, int], Collection]], y, metadata=None):
        """
        Fit the model by applying fusion, filtering and fitting the model.

        Parameters
        ----------
        X : Union[pd.DataFrame, Dict[Union[str, int], Collection]]
            The data to fit in the MultiIndex Pandas format or the TSFuse format.
        y : pd.Series
            The target variable.
        metadata : Dict[str, List[float]], optional, default None
            A dictionary containing the metadata of the experiment. If None, no metadata is collected.

        Returns
        -------
        None, but the model and filter should be fitted.
        """
        if isinstance(X, pd.DataFrame):
            X_pd = X
            X_tsfuse = None
        else:
            X_pd = None
            X_tsfuse = X

        self.task = detect_task(y) if self.task == 'auto' else self.task
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            if self.series_fusion:
                print("     Series to series")
                start_fusion = time.process_time()
                X_tsfuse = get_tsfuse_format(X, views=self.views, add_tags=self.add_tags)
                data = self.tsfuse_extractor.initialize(X_tsfuse, y)
                self.tsfuse_extractor.series_to_series(data, metadata, select_non_redundant=False)
                X_tsfuse = self.tsfuse_extractor.get_selected_series(data)
                X_tsfuse = {str(k): v for k, v in X_tsfuse.items()}
                print("         Number of fused signals: ", len(self.tsfuse_extractor.series_))
                print("         Fusion time: ", time.process_time() - start_fusion)

            if self.series_filter is not None:
                print("     Filtering series")
                start = time.process_time()
                if X_tsfuse is None:
                    self.series_filter.fit(X_pd, y, metadata)
                    X_pd = X_pd[self.series_filter.filtered_series]
                else:
                    self.series_filter.fit(X_tsfuse, y, metadata)
                    X_tsfuse = {k: v for k, v in X_tsfuse.items() if k in self.series_filter.filtered_series}
                if self.series_fusion:
                    self.tsfuse_extractor.set_subset_selected_series(self.series_filter.filtered_series)
                metadata[Keys.time_series_filtering].append(time.process_time() - start)
                print("         Number of series after filtering: ", len(self.series_filter.filtered_series))
                print("         Total filtering time: ", time.process_time() - start)

            # After filtering because fewer nodes should be added then
            if self.series_fusion:
                for n in self.tsfuse_extractor.series_:
                    n._is_output = True
                    new_node = self.tsfuse_extractor.graph_.add_node(n)
                    if isinstance(n, (Input, int, str)):
                        self.included_inputs.append(n)
                        self.nodes_translation[new_node.name] = n
                    else:
                        self.nodes_translation[new_node] = n

            # Data is still in TSFuse format
            if X_pd is None or (self.series_filter is not None and self.series_fusion):
                X_pd = dict_collection_to_pd_multiindex(X_tsfuse, index=X_pd.index if X_pd is not None else None)

            print("     Executing model")
            start = time.process_time()
            self.fit_model(X_pd, y)
            if metadata:
                metadata[Keys.time_series_to_attr].append(time.process_time() - start)
        return None
